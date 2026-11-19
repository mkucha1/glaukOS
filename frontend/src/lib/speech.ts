export const speechSupported = typeof window !== 'undefined' && 'speechSynthesis' in window;

const LANGS: Record<string, string> = { pl: 'pl-PL', en: 'en-US', tl: 'fil-PH', fil: 'fil-PH', uk: 'uk-UA', ru: 'ru-RU' };

/** "pl" -> "pl-PL"; passes full BCP-47 tags through. */
export const toBcp47 = (lang?: string) => (!lang ? 'en-US' : lang.includes('-') ? lang : (LANGS[lang] ?? 'en-US'));

export function speak(text: string, lang = 'en-US'): Promise<void> {
  if (!speechSupported) return Promise.resolve();
  const synth = window.speechSynthesis;
  synth.cancel();
  return new Promise((resolve) => {
    const u = new SpeechSynthesisUtterance(text);
    u.lang = lang;
    u.rate = 0.95;
    const voice =
      synth.getVoices().find((v) => v.lang === lang) ??
      synth.getVoices().find((v) => v.lang.startsWith(lang.slice(0, 2)));
    if (voice) u.voice = voice;
    u.onend = () => resolve();
    u.onerror = () => resolve();
    synth.speak(u);
  });
}

export function stopSpeaking() {
  if (speechSupported) window.speechSynthesis.cancel();
}
