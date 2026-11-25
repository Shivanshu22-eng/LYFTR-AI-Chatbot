import React, { useState, useRef } from 'react';
import { analyzeImage } from '../api';

const ALLOWED_EXTS = ['.jpg', '.jpeg', '.png', '.webp'];
const ALLOWED_TYPES = ['image/jpeg', 'image/jpg', 'image/png', 'image/webp'];
const MAX_BYTES = 5 * 1024 * 1024;

export function validateImageFile(file) {
  if (!file) return 'No file selected.';
  const name = (file.name || '').toLowerCase();
  const hasAllowedExt = ALLOWED_EXTS.some((ext) => name.endsWith(ext));
  const hasAllowedMime = ALLOWED_TYPES.includes((file.type || '').toLowerCase());
  if (!hasAllowedExt && !hasAllowedMime) {
    return 'Unsupported format. Please select a JPG, JPEG, PNG, or WEBP image.';
  }
  if (file.size > MAX_BYTES) {
    return 'Image exceeds the 5 MB limit.';
  }
  return null;
}

export default function ImageAnalysisPanel({ activeSession, onError }) {
  const [file, setFile] = useState(null);
  const [previewUrl, setPreviewUrl] = useState(null);
  const [prompt, setPrompt] = useState('');
  const [dragOver, setDragOver] = useState(false);
  const [loading, setLoading] = useState(false);
  const [result, setResult] = useState(null);
  const fileInputRef = useRef(null);

  const handleSelectFile = (f) => {
    if (!f) return;
    const err = validateImageFile(f);
    if (err) {
      onError?.(err);
      return;
    }
    if (previewUrl) URL.revokeObjectURL(previewUrl);
    setFile(f);
    setPreviewUrl(URL.createObjectURL(f));
    setResult(null);
  };

  const handleClear = () => {
    if (previewUrl) URL.revokeObjectURL(previewUrl);
    setFile(null);
    setPreviewUrl(null);
    if (fileInputRef.current) fileInputRef.current.value = '';
  };

  const handleAnalyze = async (e) => {
    e.preventDefault();
    if (!file || loading) return;
    setLoading(true);
    try {
      const data = await analyzeImage(file, prompt, activeSession);
      setResult(data);
    } catch (err) {
      onError?.(err.message);
    } finally {
      setLoading(false);
    }
  };

  return (
    <section className="feature-panel" data-testid="image-analysis-panel">
      <div className="panel-header">
        <h2>🖼️ Multimodal Image Analysis</h2>
        <p>Upload JPG, JPEG, PNG, or WEBP images for Gemini vision & agricultural crop analysis.</p>
      </div>

      <form className="panel-card" onSubmit={handleAnalyze}>
        <div
          className={`dropzone ${dragOver ? 'drag-over' : ''}`}
          onDragOver={(e) => { e.preventDefault(); setDragOver(true); }}
          onDragLeave={() => setDragOver(false)}
          onDrop={(e) => {
            e.preventDefault();
            setDragOver(false);
            handleSelectFile(e.dataTransfer.files?.[0]);
          }}
          onClick={() => fileInputRef.current?.click()}
        >
          <input
            ref={fileInputRef}
            type="file"
            accept=".jpg,.jpeg,.png,.webp,image/jpeg,image/png,image/webp"
            hidden
            onChange={(e) => handleSelectFile(e.target.files?.[0])}
          />
          {previewUrl ? (
            <div className="preview-box" onClick={(e) => e.stopPropagation()}>
              <img src={previewUrl} alt="Selected preview" className="preview-img" />
              <div className="preview-info">
                <span>{file?.name} ({Math.round((file?.size || 0) / 1024)} KB)</span>
                <button type="button" className="btn-secondary" onClick={handleClear}>
                  Remove
                </button>
              </div>
            </div>
          ) : (
            <div className="dropzone-placeholder">
              <span className="drop-icon">📷</span>
              <span>Drag & drop an image here, or click to browse</span>
              <small>JPG, JPEG, PNG, WEBP • Max 5 MB</small>
            </div>
          )}
        </div>

        <div className="preset-row">
          <button
            type="button"
            className="chip-btn"
            onClick={() => setPrompt('Identify visible crop characteristics, any disease symptoms or pest damage, and state whether yield can be estimated with uncertainty.')}
          >
            🌾 Crop & Disease Check
          </button>
          <button
            type="button"
            className="chip-btn"
            onClick={() => setPrompt('Inspect leaf color, spots, wilting, or nutrient deficiency symptoms.')}
          >
            🍃 Leaf Health Scan
          </button>
          <button
            type="button"
            className="chip-btn"
            onClick={() => setPrompt('Describe everything visible in this image in detail.')}
          >
            🔍 General Description
          </button>
        </div>

        <div className="form-row">
          <input
            type="text"
            className="text-input"
            value={prompt}
            onChange={(e) => setPrompt(e.target.value)}
            placeholder="Optional question about the image (e.g., What disease is on these leaves?)"
          />
          <button type="submit" className="btn-primary" disabled={!file || loading}>
            {loading ? 'Analyzing…' : 'Analyze Image'}
          </button>
        </div>
      </form>

      {result && (
        <div className="panel-card result-card">
          <div className="result-header">
            <h3>Analysis Result — {result.filename}</h3>
            <span className="badge badge-live">
              {result.metadata?.resolution_source || 'LIVE_INFERENCE'} (Cache Bypassed)
            </span>
          </div>
          <div className="analysis-text">{result.analysis}</div>
          {result.metadata && (
            <div className="message-meta">
              {result.metadata.model && <span className="meta-tag">🧠 {result.metadata.model}</span>}
              {result.metadata.latency_ms != null && <span className="meta-tag">⏱ {result.metadata.latency_ms}ms</span>}
              {result.metadata.input_tokens != null && <span className="meta-tag">📥 {result.metadata.input_tokens}</span>}
              {result.metadata.output_tokens != null && <span className="meta-tag">📤 {result.metadata.output_tokens}</span>}
              {result.metadata.key_id && <span className="meta-tag meta-key">🔑 {result.metadata.key_id}</span>}
            </div>
          )}
        </div>
      )}
    </section>
  );
}
