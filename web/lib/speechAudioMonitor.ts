/** @deprecated Import from @/lib/speech/audioLevel */
export {
  createAudioLevelMonitor,
  sampleMicLevel,
} from "@/lib/speech/audioLevel";
export {
  getStreamMicLabel as getActiveMicLabel,
  enumerateAudioInputs as listAudioInputDeviceLabels,
} from "@/lib/speech/devices";
