const API_BASE_URL = (import.meta.env.VITE_API_BASE_URL || '').replace(/\/$/, '');

export async function analyzeVideo(videoBlob) {
  const formData = new FormData();
  formData.append('video', videoBlob, 'session.webm');

  let response;
  try {
    response = await fetch(`${API_BASE_URL}/api/analyze`, {
      method: 'POST',
      body: formData,
    });
  } catch {
    throw new Error(
      'Backend tidak dapat dihubungi. Pastikan Flask/Render aktif dan VITE_API_BASE_URL benar.',
    );
  }

  const text = await response.text();
  let data;
  try {
    data = JSON.parse(text);
  } catch {
    throw new Error(`Endpoint mengembalikan HTTP ${response.status}`);
  }

  if (!response.ok) {
    if (response.status === 403) {
      throw new Error('Akses API ditolak (403). Periksa URL backend dan konfigurasi deployment.');
    }
    throw new Error(data.message || data.error || `HTTP ${response.status}`);
  }

  if (!data.predictions) {
    throw new Error(data.message || 'Hasil analisis belum tersedia.');
  }

  return data;
}
