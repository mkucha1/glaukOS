// MediaRecorder wrapper. The mic stream is opened once and kept, so push-to-talk starts instantly.

const CANDIDATES = [
  'audio/webm;codecs=opus', // Chrome / Android
  'audio/webm',
  'audio/mp4;codecs=mp4a.40.2', // iOS Safari
  'audio/mp4',
  'audio/aac',
];

export function pickMime(): string | undefined {
  if (typeof MediaRecorder === 'undefined') return undefined;
  return CANDIDATES.find((m) => MediaRecorder.isTypeSupported(m));
}

export interface Recording {
  blob: Blob;
  mime: string;
  durationMs: number;
}

export class Recorder {
  private stream: MediaStream | null = null;
  private rec: MediaRecorder | null = null;
  private chunks: Blob[] = [];
  private startedAt = 0;

  get ready() {
    return !!this.stream && this.stream.getAudioTracks().some((t) => t.readyState === 'live');
  }

  async ensureStream() {
    if (this.ready) return;
    if (!navigator.mediaDevices?.getUserMedia) {
      throw new Error('Microphone needs HTTPS (or localhost).');
    }
    this.stream = await navigator.mediaDevices.getUserMedia({
      audio: { echoCancellation: true, noiseSuppression: true, autoGainControl: true },
    });
  }

  async start() {
    await this.ensureStream();
    const mime = pickMime();
    this.chunks = [];
    this.rec = new MediaRecorder(this.stream!, mime ? { mimeType: mime } : undefined);
    this.rec.ondataavailable = (e) => e.data.size && this.chunks.push(e.data);
    this.rec.start(250);
    this.startedAt = performance.now();
  }

  get recording() {
    return this.rec?.state === 'recording';
  }

  stop(): Promise<Recording> {
    const rec = this.rec;
    return new Promise((resolve, reject) => {
      if (!rec || rec.state === 'inactive') return reject(new Error('not recording'));
      rec.onstop = () => {
        const mime = rec.mimeType || pickMime() || 'audio/webm';
        resolve({
          blob: new Blob(this.chunks, { type: mime }),
          mime,
          durationMs: performance.now() - this.startedAt,
        });
        this.rec = null;
      };
      rec.stop();
    });
  }
}

export const recorder = new Recorder();
