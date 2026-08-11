import { useEffect, useRef, useState } from 'react';

// Leave empty when React is served by Flask. For a separate host (Vercel, etc.),
// set VITE_API_BASE_URL to the public Flask/Render URL.
const API_BASE_URL = (import.meta.env.VITE_API_BASE_URL || '').replace(/\/$/, '');

function AnalysisModal({ analysis, onClose }) {
  if (!analysis) return null;

  return (
    <div className="recap-modal" role="presentation" onClick={(event) => event.target === event.currentTarget && onClose()}>
      <section className="recap-card" role="dialog" aria-modal="true" aria-labelledby="recap-title">
        <div className="result-head">
          <h2 id="recap-title" className="result-title">Rekap analisis</h2>
          <span className="score">{analysis.score}/100</span>
        </div>
        <div className="summary-list">
          {Object.entries(analysis.predictions).map(([name, item]) => (
            <div className="summary-row" key={name}>
              <span className="metric">{name}</span>
              <span className="metric-value">{item.label}</span>
              <span className="confidence">{Math.round(item.confidence * 100)}%</span>
            </div>
          ))}
        </div>
        <button className="close" type="button" onClick={onClose}>Tutup rekap</button>
      </section>
    </div>
  );
}

export default function App() {
  const videoRef = useRef(null);
  const recorderRef = useRef(null);
  const streamRef = useRef(null);
  const chunksRef = useRef([]);
  const [cameraReady, setCameraReady] = useState(false);
  const [isRecording, setIsRecording] = useState(false);
  const [status, setStatus] = useState('Belum ada sesi analisis.');
  const [analysis, setAnalysis] = useState(null);
  const [isRecapOpen, setIsRecapOpen] = useState(false);

  useEffect(() => () => streamRef.current?.getTracks().forEach((track) => track.stop()), []);

  async function startCamera() {
    try {
      const stream = await navigator.mediaDevices.getUserMedia({ video: true, audio: true });
      streamRef.current = stream;
      videoRef.current.srcObject = stream;
      setCameraReady(true);
      setStatus('Kamera aktif. Siap merekam.');
    } catch (error) {
      setStatus(`Kamera tidak bisa dibuka: ${error.message}`);
    }
  }

  function startRecording() {
    chunksRef.current = [];
    const recorder = new MediaRecorder(streamRef.current);
    recorderRef.current = recorder;
    recorder.ondataavailable = (event) => event.data.size && chunksRef.current.push(event.data);
    recorder.onstop = analyzeRecording;
    recorder.start();
    setIsRecording(true);
    setAnalysis(null);
    setStatus('Sedang merekam...');
  }

  function stopRecording() {
    recorderRef.current?.stop();
    setIsRecording(false);
    setStatus('Mengirim sesi untuk dianalisis...');
  }

  async function analyzeRecording() {
    const form = new FormData();
    form.append('video', new Blob(chunksRef.current, { type: 'video/webm' }), 'session.webm');

    try {
      const response = await fetch(`${API_BASE_URL}/api/analyze`, { method: 'POST', body: form });
      const text = await response.text();
      let data;
      try {
        data = JSON.parse(text);
      } catch {
        throw new Error(`Endpoint mengembalikan HTTP ${response.status}`);
      }
      if (!response.ok) {
        if (response.status === 403) {
          throw new Error('Akses API ditolak (403). Pastikan VITE_API_BASE_URL mengarah ke backend Flask/Render.');
        }
        throw new Error(data.message || data.error || `HTTP ${response.status}`);
      }
      if (!data.predictions) throw new Error(data.message || 'Hasil analisis belum tersedia.');
      setAnalysis(data);
      setStatus('Analisis berhasil. Hasil rekap siap dilihat.');
    } catch (error) {
      const message = error instanceof TypeError
        ? 'Backend tidak dapat dihubungi. Pastikan Flask/Render aktif dan VITE_API_BASE_URL mengarah ke URL backend yang benar.'
        : error.message;
      setStatus(`Gagal menganalisis video: ${message}`);
    }
  }

  return (
    <>
      <main>
        <p className="eyebrow">AI Presentation Coach</p>
        <h1>Latih presentasimu dengan percaya diri</h1>
        <p className="intro">Rekam sesi latihan dan dapatkan rekap analisis gerakan serta postur tubuhmu.</p>
        <video ref={videoRef} autoPlay muted playsInline />
        <div className="controls">
          <button type="button" onClick={startCamera} disabled={cameraReady}>Mulai kamera</button>
          <button type="button" onClick={startRecording} disabled={!cameraReady || isRecording}>Mulai rekam</button>
          <button type="button" className="secondary" onClick={stopRecording} disabled={!isRecording}>Berhenti &amp; analisis</button>
        </div>
        <div className="status" aria-live="polite">{status}</div>
        {analysis && <button className="recap-trigger" type="button" onClick={() => setIsRecapOpen(true)}>Lihat hasil rekap</button>}
      </main>
      {isRecapOpen && <AnalysisModal analysis={analysis} onClose={() => setIsRecapOpen(false)} />}
    </>
  );
}
