// realtime_transcriber_client.js (replaces MediaRecorder loop)

let socket;
let audioContext;
let processor;
let input;
let globalStream;

const status = document.getElementById('status');
const replyAudio = document.getElementById('replyAudio');
const responseText = document.getElementById('responseText');

function setStatus(state) {
  status.className = state;
  status.textContent =
    state === 'listening' ? 'Listening...' :
    state === 'thinking' ? 'Thinking...' :
    state === 'speaking' ? 'Speaking...' :
    'Idle';
}

function initWebSocket() {
  socket = new WebSocket('wss://' + window.location.host + '/stream-audio');

  socket.onopen = () => {
    setStatus('listening');
    console.log('WebSocket connected');
  };

  socket.onmessage = (event) => {
    const data = JSON.parse(event.data);
    if (data.text) {
      responseText.textContent = data.text;
    }
    if (data.audio_b64) {
      const audioBlob = new Blob([
        Uint8Array.from(atob(data.audio_b64), c => c.charCodeAt(0))
      ], { type: 'audio/wav' });
      replyAudio.src = URL.createObjectURL(audioBlob);
      replyAudio.play();
      setStatus('speaking');
      replyAudio.onended = () => setStatus('listening');
    }
  };

  socket.onerror = (e) => {
    console.error('WebSocket error:', e);
    setStatus('error');
  };

  socket.onclose = () => {
    console.log('WebSocket closed');
    setStatus('idle');
  };
}

async function startStreamingAudio() {
  audioContext = new AudioContext({ sampleRate: 16000 });
  globalStream = await navigator.mediaDevices.getUserMedia({ audio: true });
  input = audioContext.createMediaStreamSource(globalStream);
  processor = audioContext.createScriptProcessor(4096, 1, 1);

  processor.onaudioprocess = (e) => {
    const inputData = e.inputBuffer.getChannelData(0);
    const int16Data = convertFloat32ToInt16(inputData);
    if (socket && socket.readyState === 1) {
      socket.send(int16Data);
    }
  };

  input.connect(processor);
  processor.connect(audioContext.destination);
}

function convertFloat32ToInt16(buffer) {
  let l = buffer.length;
  const result = new Int16Array(l);
  for (let i = 0; i < l; i++) {
    result[i] = Math.min(1, buffer[i]) * 0x7FFF;
  }
  return result.buffer;
}

window.onload = () => {
  initWebSocket();
  startStreamingAudio();
};
