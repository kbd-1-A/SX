export type AudioStopper = () => void

/** 页面内唯一主音频会话：TTS 和音乐不能同时占用音频焦点。 */
export class AudioFocusManager {
  private speechStopper: AudioStopper | null = null
  private musicStoppers = new Map<string, AudioStopper>()

  setSpeechStopper(stopper: AudioStopper | null) {
    this.speechStopper = stopper
  }

  registerMusicStopper(id: string, stopper: AudioStopper) {
    this.musicStoppers.set(id, stopper)
    return () => this.musicStoppers.delete(id)
  }

  claimMusic(id: string) {
    this.speechStopper?.()
    for (const [otherId, stopper] of this.musicStoppers) {
      if (otherId !== id) stopper()
    }
  }

  claimSpeech() {
    for (const stopper of this.musicStoppers.values()) stopper()
  }
}

export const audioFocus = new AudioFocusManager()
