// realtime_transcriber_client.js (Streaming to Azure GPT-4o Realtime)

let socket;
let audioContext;
let processor;
let input;
let globalStream;

const status = document.getElementById('status');
const replyAudio = document.getElementById('replyAudio');
const conversation = document.getElementById('responseText');

function setStatus(state) {
  status.className = state;
  status.textContent =
    state === 'listening' ? 'Listening...'
    : state === 'thinking' ? 'Thinking...'
    : state === 'speaking' ? 'Speaking...'
    : 'Idle';
}

function appendToConversation(role, text) {
  const p = document.createElement('p');
  p.textContent = `${role === 'user' ? '🟢 You' : '🤖 Assistant'}: ${text}`;
  conversation.appendChild(p);
  conversation.scrollTop = conversation.scrollHeight;
}

function initWebSocket() {
  const AZURE_WS_URI = "wss://admin-m7q8p9qe-eastus2.cognitiveservices.azure.com/openai/realtime?api-version=2024-10-01-preview&deployment=gpt-4o-mini-realtime-preview&api-key=YOUR_AZURE_API_KEY";
  socket = new WebSocket(AZURE_WS_URI);

  socket.onopen = () => {
    setStatus('listening');
    console.log('✅ WebSocket connected');
    socket.send(JSON.stringify({
      type: "session.update",
      session: {
        modalities: ["audio"],
        instructions: "You are a helpful form-filling assistant. Ask questions one by one and extract values."
      }
    }));
    socket.send(JSON.stringify({ type: "response.create" }));

    // 🗣️ Send initial welcome message like original assistant
    socket.send(JSON.stringify({
      type: "conversation.item.create",
      item: {
        type: "message",
        role: "user",
        content: [
          {
            type: "input_text",
            text: "Hello, can we get started by telling me the first steps?"
          }
        ]
      }
    }));
  };

  socket.onmessage = (event) => {
    const msg = JSON.parse(event.data);
    const type = msg.type;

    if (type === "response.text") {
      const partial = msg.text;
      console.log("✏️ Partial:", partial);
    }
    if (type === "response.text.done") {
      const finalText = msg.text;
      appendToConversation('assistant', finalText);
      setStatus('speaking');
      synthesizeSpeech(finalText);
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

async function synthesizeSpeech(text) {
  const response = await fetch("/tts", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ text })
  });
  const { audio_b64 } = await response.json();

  const audioBlob = new Blob([
    Uint8Array.from(atob(audio_b64), c => c.charCodeAt(0))
  ], { type: 'audio/wav' });
  replyAudio.src = URL.createObjectURL(audioBlob);
  replyAudio.play();
  replyAudio.onended = () => setStatus('listening');
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
    const int16Data = convertFloat32ToInt16(inputData);

    if (socket && socket.readyState === 1) {
      const base64Audio = btoa(
        String.fromCharCode(...new Uint8Array(int16Data))
      );

      socket.send(JSON.stringify({
        type: "input.audio",
        audio: base64Audio
      }));
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
