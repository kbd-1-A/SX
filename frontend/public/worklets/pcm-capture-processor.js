class PcmCaptureProcessor extends AudioWorkletProcessor {
  process(inputs) {
    const channel = inputs[0] && inputs[0][0]
    if (!channel) return true

    const copy = new Float32Array(channel.length)
    copy.set(channel)
    this.port.postMessage(copy.buffer, [copy.buffer])
    return true
  }
}

registerProcessor('pcm-capture-processor', PcmCaptureProcessor)
