"""Optional voice I/O. Install with: pip install -r requirements-voice.txt"""


class VoiceUnavailable(RuntimeError):
    pass


class Voice:
    def __init__(self):
        try:
            import pyttsx3
            import speech_recognition as sr
        except ImportError as e:
            raise VoiceUnavailable("voice extras not installed: pip install -r requirements-voice.txt") from e
        self._sr = sr
        self.recognizer = sr.Recognizer()
        self.tts = pyttsx3.init()

    def listen(self, timeout: float = 5, phrase_limit: float = 15) -> str | None:
        with self._sr.Microphone() as source:
            self.recognizer.adjust_for_ambient_noise(source, duration=0.5)
            try:
                audio = self.recognizer.listen(source, timeout=timeout, phrase_time_limit=phrase_limit)
                return self.recognizer.recognize_google(audio)
            except (self._sr.WaitTimeoutError, self._sr.UnknownValueError):
                return None

    def speak(self, text: str) -> None:
        self.tts.say(text)
        self.tts.runAndWait()
