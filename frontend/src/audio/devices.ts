export interface AudioInputDevice {
  deviceId: string
  label: string
}

export async function listAudioInputs(): Promise<AudioInputDevice[]> {
  if (!navigator.mediaDevices?.enumerateDevices) return []
  const devices = await navigator.mediaDevices.enumerateDevices()
  let unnamed = 0
  return devices
    .filter((device) => device.kind === 'audioinput')
    .map((device) => {
      unnamed += device.label ? 0 : 1
      return {
        deviceId: device.deviceId,
        label: device.label || `麦克风 ${unnamed}`,
      }
    })
}
