// realtime_transcriber_client.js

let socket;
let audioContext;
let processor;
let input;
let globalStream;

const status = document.getElementById('status');
const replyAudio = document.getElementById('replyAudio');

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
    console.log('✅ WebSocket connected');
  };

  socket.onmessage = (event) => {
    const data = JSON.parse(event.data);
    if (data.text) {
      console.log('🤖 Assistant:', data.text);
      setStatus('speaking');
      window.appendAssistant?.(data.text);
    }
    if (data.audio_b64) {
      console.log('🎧 Received audio response');
      const audioBlob = new Blob([
        Uint8Array.from(atob(data.audio_b64), c => c.charCodeAt(0))
      ], { type: 'audio/wav' });
      replyAudio.src = URL.createObjectURL(audioBlob);
      replyAudio.play();
      replyAudio.onended = () => setStatus('listening');
    }
  };

  socket.onerror = (e) => {
    console.error('❌ WebSocket error:', e);
    setStatus('error');
  };

  socket.onclose = () => {
    console.log('🔌 WebSocket closed');
    setStatus('idle');
  };
}

async function startStreamingAudio() {
  try {
    const hasMic = await navigator.permissions.query({ name: 'microphone' });
    if (hasMic.state !== 'granted') {
      alert('Microphone access not granted. Please allow mic to use the assistant.');
      return;
    }
  } catch (err) {
    console.warn('Mic permission query unsupported:', err);
  }

  audioContext = new AudioContext({ sampleRate: 16000 });
  globalStream = await navigator.mediaDevices.getUserMedia({ audio: true });
  input = audioContext.createMediaStreamSource(globalStream);
  processor = audioContext.createScriptProcessor(4096, 1, 1);

  processor.onaudioprocess = (e) => {
    const inputData = e.inputBuffer.getChannelData(0);
    console.log('🎙️ Captured audio frame');
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
  console.log('📡 Initializing assistant...');
  initWebSocket();
  startStreamingAudio();
};
