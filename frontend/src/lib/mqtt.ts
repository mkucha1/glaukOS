// EventBus: MQTT.js over WebSocket, Supabase Realtime, or the in-browser mock.
import mqtt, { type MqttClient } from 'mqtt';
import type { RealtimeChannel } from '@supabase/supabase-js';
import { config } from '../config';
import { removeCrew, upsertCrew, type CrewMember } from './crew';
import { supabase } from './supabase';
import { isDeadZone, mockServer } from './mock';
import { actorOf, deviceId, type Profile } from './profile';
import type { ShipEvent } from '../types';

export type BusState = 'connecting' | 'connected' | 'offline';

export interface EventBus {
  start(profile: Profile | null): void;
  stop(): void;
  onEvent(h: (e: ShipEvent) => void): () => void;
  onState(h: (s: BusState) => void): () => void;
  readonly state: BusState;
}

abstract class BaseBus implements EventBus {
  protected eventHandlers = new Set<(e: ShipEvent) => void>();
  protected stateHandlers = new Set<(s: BusState) => void>();
  state: BusState = 'offline';

  abstract start(profile: Profile | null): void;
  abstract stop(): void;

  onEvent(h: (e: ShipEvent) => void) {
    this.eventHandlers.add(h);
    return () => {
      this.eventHandlers.delete(h);
    };
  }
  onState(h: (s: BusState) => void) {
    this.stateHandlers.add(h);
    h(this.state);
    return () => {
      this.stateHandlers.delete(h);
    };
  }
  protected setState(s: BusState) {
    if (s === this.state) return;
    this.state = s;
    this.stateHandlers.forEach((h) => h(s));
  }
  protected dispatch(e: ShipEvent) {
    this.eventHandlers.forEach((h) => h(e));
  }
}

/** Without a profile (overview kiosk) only the ship-wide stream is needed. */
export const topicsFor = (p: Profile | null) =>
  p ? [`ship/${config.shipId}/events`, `person/${actorOf(p)}`, `role/${p.position}/approve`] : [`ship/${config.shipId}/events`];

class MqttBus extends BaseBus {
  private client: MqttClient | null = null;
  private topics: string[] = [];

  start(profile: Profile | null) {
    this.stop();
    this.topics = topicsFor(profile);
    this.setState('connecting');
    const client = mqtt.connect(config.mqttUrl, {
      clientId: `shipbrain-${deviceId()}`,
      clean: false, // persistent session: broker keeps QoS1 messages while we are in a dead zone
      reconnectPeriod: 2000,
      connectTimeout: 5000,
      keepalive: 20,
    });
    this.client = client;
    client.on('connect', () => {
      client.subscribe(this.topics, { qos: 1 }, (err) => err && console.error('[mqtt] subscribe', err));
      this.setState('connected');
    });
    client.on('reconnect', () => this.setState('connecting'));
    client.on('offline', () => this.setState('offline'));
    client.on('close', () => this.state === 'connected' && this.setState('offline'));
    client.on('error', (err) => console.warn('[mqtt]', err.message));
    client.on('message', (_topic, buf) => {
      try {
        this.dispatch(JSON.parse(buf.toString()) as ShipEvent);
      } catch (err) {
        console.warn('[mqtt] bad message', err);
      }
    });
  }

  stop() {
    if (!this.client) return;
    const c = this.client;
    this.client = null;
    if (c.connected && this.topics.length) c.unsubscribe(this.topics);
    c.end(true);
    this.setState('offline');
  }
}

class MockBus extends BaseBus {
  private unsub: (() => void) | null = null;
  private timer: ReturnType<typeof setInterval> | null = null;

  start() {
    this.stop();
    this.unsub = mockServer.subscribe((e) => this.dispatch(e));
    const check = () => this.setState(navigator.onLine && !isDeadZone() ? 'connected' : 'offline');
    check();
    this.timer = setInterval(check, 1000);
  }

  stop() {
    this.unsub?.();
    this.unsub = null;
    if (this.timer) clearInterval(this.timer);
    this.timer = null;
    this.setState('offline');
  }
}

/** Supabase Realtime: inserts into public.events (filtered by RLS) and crew duty changes. */
class SupabaseBus extends BaseBus {
  private channel: RealtimeChannel | null = null;

  start(profile: Profile | null) {
    this.stop();
    if (!supabase || !profile) return; // RLS shows nothing without a signed-in crew member
    this.setState('connecting');
    this.channel = supabase
      .channel('glaukos-register')
      .on('postgres_changes', { event: 'INSERT', schema: 'public', table: 'events' }, (p) => this.dispatch(p.new as ShipEvent))
      .on('postgres_changes', { event: '*', schema: 'public', table: 'crew' }, (p) => {
        if (p.eventType === 'DELETE') removeCrew((p.old as { id: string }).id);
        else upsertCrew(p.new as CrewMember);
      })
      .subscribe((status) => {
        if (status === 'SUBSCRIBED') this.setState('connected');
        else if (status === 'CHANNEL_ERROR' || status === 'TIMED_OUT') this.setState('connecting');
        else if (status === 'CLOSED') this.setState('offline');
      });
  }

  stop() {
    if (this.channel) void supabase?.removeChannel(this.channel);
    this.channel = null;
    this.setState('offline');
  }
}

export const bus: EventBus = config.backend === 'mock' ? new MockBus() : config.backend === 'supabase' ? new SupabaseBus() : new MqttBus();
