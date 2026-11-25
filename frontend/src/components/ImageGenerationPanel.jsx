import React, { useState, useRef, useCallback } from 'react';
import { generateImage, fetchImageHistory } from '../api.js';

const STYLES = [
  { value: 'photorealistic', label: '📷 Photorealistic' },
  { value: 'cinematic', label: '🎬 Cinematic' },
  { value: 'anime', label: '🎌 Anime' },
  { value: 'digital_art', label: '🎨 Digital Art' },
  { value: '3d_rendering', label: '🧊 3D Rendering' },
  { value: 'illustration', label: '✏️ Illustration' },
  { value: 'watercolor', label: '🖌️ Watercolor' },
  { value: 'fantasy', label: '🧙 Fantasy' },
  { value: 'architecture', label: '🏛️ Architecture' },
  { value: 'product_photography', label: '📦 Product Photo' },
];

const RATIOS = [
  { value: '1:1', label: '■ 1:1', desc: 'Square' },
  { value: '16:9', label: '▬ 16:9', desc: 'Landscape' },
  { value: '9:16', label: '▮ 9:16', desc: 'Portrait' },
  { value: '4:3', label: '▬ 4:3', desc: 'Standard' },
  { value: '3:2', label: '▬ 3:2', desc: 'Photo' },
];

const EXAMPLE_PROMPTS = [
  'A majestic eagle soaring over snow-capped mountains at golden hour',
  'Futuristic city skyline with flying cars at night, neon lights',
  'A serene Japanese zen garden with cherry blossoms and koi pond',
  'Dramatic portrait of a lion in the savanna at sunset',
  'Ancient library with floating books and magical glowing orbs',
  'Healthy wheat field with blue sky and white clouds, aerial view',
];

export default function ImageGenerationPanel({ user }) {
  const [prompt, setPrompt] = useState('');
  const [style, setStyle] = useState('photorealistic');
  const [ratio, setRatio] = useState('1:1');
  const [numImages, setNumImages] = useState(1);
  const [generating, setGenerating] = useState(false);
  const [results, setResults] = useState(null);
  const [error, setError] = useState('');
  const [history, setHistory] = useState([]);
  const [showHistory, setShowHistory] = useState(false);
  const [historyLoading, setHistoryLoading] = useState(false);
  const [progress, setProgress] = useState('');
  const galleryRef = useRef(null);

  const handleGenerate = async () => {
    if (!prompt.trim()) {
      setError('Please enter a prompt to generate images.');
      return;
    }
    setError('');
    setGenerating(true);
    setResults(null);
    setProgress(`Generating ${numImages} image${numImages > 1 ? 's' : ''}…`);

    try {
      const data = await generateImage(prompt.trim(), style, ratio, numImages);
      setResults(data);
      setProgress('');
      // Scroll to gallery
      setTimeout(() => galleryRef.current?.scrollIntoView({ behavior: 'smooth' }), 100);
    } catch (err) {
      setError(err.message || 'Image generation failed.');
      setProgress('');
    } finally {
      setGenerating(false);
    }
  };

  const loadHistory = async () => {
    setHistoryLoading(true);
    try {
      const records = await fetchImageHistory(20);
      setHistory(records);
      setShowHistory(true);
    } catch (err) {
      setError('Failed to load history: ' + err.message);
    } finally {
      setHistoryLoading(false);
    }
  };

  const downloadImage = useCallback(async (imgUrl, index) => {
    try {
      const link = document.createElement('a');
      link.href = imgUrl;
      link.download = `lyftr-ai-image-${index}.png`;
      link.target = '_blank';
      link.rel = 'noopener noreferrer';
      link.click();
    } catch (err) {
      window.open(imgUrl, '_blank');
    }
  }, []);

  const canGenerate = user && (user.role === 'admin' || user.role === 'authorized_creator' || user.role === 'user');

  return (
    <div className="feature-panel image-gen-panel">
      <div className="panel-header">
        <h2>🎨 AI Image Generation Studio</h2>
        <p className="panel-subtitle">
          Generate stunning AI images with Pollinations.ai · Flux model
          {user && <span className="user-role-badge role-{user.role}">{user.role}</span>}
        </p>
      </div>

      {/* Prompt Area */}
      <div className="panel-card">
        <label className="field-label">✍️ Describe your image</label>
        <textarea
          className="prompt-textarea"
          value={prompt}
          onChange={(e) => setPrompt(e.target.value)}
          placeholder="A photorealistic portrait of a wise old farmer in golden hour light, detailed face, shallow depth of field…"
          rows={4}
          maxLength={2000}
          disabled={generating}
        />
        <div className="prompt-footer">
          <span className="char-count">{prompt.length}/2000</span>
          <div className="example-chips">
            {EXAMPLE_PROMPTS.slice(0, 3).map((p, i) => (
              <button key={i} className="chip" onClick={() => setPrompt(p)} disabled={generating}>
                💡 Example {i + 1}
              </button>
            ))}
          </div>
        </div>
      </div>

      {/* Controls */}
      <div className="gen-controls-grid">
        {/* Style */}
        <div className="panel-card">
          <label className="field-label">🎭 Artistic Style</label>
          <div className="style-grid">
            {STYLES.map((s) => (
              <button
                key={s.value}
                className={`style-btn ${style === s.value ? 'active' : ''}`}
                onClick={() => setStyle(s.value)}
                disabled={generating}
              >
                {s.label}
              </button>
            ))}
          </div>
        </div>

        {/* Ratio & Count */}
        <div className="panel-card">
          <label className="field-label">📐 Aspect Ratio</label>
          <div className="ratio-grid">
            {RATIOS.map((r) => (
              <button
                key={r.value}
                className={`ratio-btn ${ratio === r.value ? 'active' : ''}`}
                onClick={() => setRatio(r.value)}
                disabled={generating}
                title={r.desc}
              >
                {r.label}
                <small>{r.desc}</small>
              </button>
            ))}
          </div>

          <label className="field-label" style={{ marginTop: '1rem' }}>🔢 Number of Variations</label>
          <div className="num-selector">
            {[1, 2, 3, 4].map((n) => (
              <button
                key={n}
                className={`num-btn ${numImages === n ? 'active' : ''}`}
                onClick={() => setNumImages(n)}
                disabled={generating}
              >
                {n}
              </button>
            ))}
          </div>
        </div>
      </div>

      {/* Generate Button */}
      {error && <div className="error-banner">⚠️ {error}</div>}
      {progress && (
        <div className="progress-banner">
          <span className="spinner" /> {progress}
        </div>
      )}

      <div className="gen-actions">
        <button
          className="btn-generate"
          onClick={handleGenerate}
          disabled={generating || !prompt.trim()}
        >
          {generating ? '⏳ Generating…' : '✨ Generate Image'}
        </button>
        <button
          className="btn-secondary"
          onClick={loadHistory}
          disabled={historyLoading}
        >
          {historyLoading ? '⏳ Loading…' : '📋 My History'}
        </button>
      </div>

      {/* Results Gallery */}
      {results && (
        <div className="panel-card" ref={galleryRef}>
          <div className="gallery-header">
            <h3>🖼️ Generated Images</h3>
            <span className="meta-badge">{results.provider} · {results.model}</span>
          </div>
          {results.errors && results.errors.length > 0 && (
            <div className="warning-banner">
              ⚠️ {results.errors.length} variation(s) failed: {results.errors[0]}
            </div>
          )}
          <div className={`image-gallery cols-${results.images.length}`}>
            {results.images.map((img, i) => (
              <div key={i} className="image-card">
                <div className="image-wrapper">
                  <img
                    src={img.image_url}
                    alt={`Generated: ${results.prompt}`}
                    loading="lazy"
                    onError={(e) => {
                      e.target.style.display = 'none';
                      e.target.nextSibling.style.display = 'flex';
                    }}
                  />
                  <div className="image-error-state" style={{ display: 'none' }}>
                    <span>⚠️ Image loading…</span>
                    <a href={img.image_url} target="_blank" rel="noopener noreferrer">
                      Open directly
                    </a>
                  </div>
                </div>
                <div className="image-card-footer">
                  <span className="variation-label">Variation {img.variation_index}</span>
                  <div className="image-actions">
                    <button
                      className="btn-icon"
                      onClick={() => downloadImage(img.image_url, i + 1)}
                      title="Download"
                    >
                      ⬇️ Download
                    </button>
                    <a
                      href={img.image_url}
                      target="_blank"
                      rel="noopener noreferrer"
                      className="btn-icon"
                    >
                      🔗 Open
                    </a>
                  </div>
                </div>
              </div>
            ))}
          </div>
          <div className="generation-meta">
            <span>⏱️ {results.latency_ms ? `${Math.round(results.latency_ms)}ms` : 'N/A'}</span>
            <span>📐 {ratio}</span>
            <span>🎭 {STYLES.find((s) => s.value === style)?.label || style}</span>
          </div>
          <button
            className="btn-regenerate"
            onClick={handleGenerate}
            disabled={generating}
          >
            🔄 Regenerate
          </button>
        </div>
      )}

      {/* History */}
      {showHistory && (
        <div className="panel-card">
          <div className="gallery-header">
            <h3>📋 Generation History</h3>
            <button className="btn-link" onClick={() => setShowHistory(false)}>Hide</button>
          </div>
          {history.length === 0 ? (
            <p className="empty-state">No generation history yet.</p>
          ) : (
            <div className="history-grid">
              {history.map((rec) => (
                <div key={rec.id} className={`history-card status-${rec.status}`}>
                  <div className="history-prompt">{rec.prompt.slice(0, 80)}{rec.prompt.length > 80 ? '…' : ''}</div>
                  <div className="history-meta">
                    <span className={`status-badge ${rec.status}`}>{rec.status}</span>
                    <span>{rec.style}</span>
                    <span>{rec.aspect_ratio}</span>
                    <span>{new Date(rec.created_at).toLocaleDateString()}</span>
                  </div>
                  {rec.images && rec.images.length > 0 && (
                    <div className="history-thumbs">
                      {rec.images.slice(0, 3).map((img, i) => (
                        <img
                          key={i}
                          src={img.image_url}
                          alt="thumbnail"
                          className="history-thumb"
                          onClick={() => window.open(img.image_url, '_blank')}
                        />
                      ))}
                    </div>
                  )}
                </div>
              ))}
            </div>
          )}
        </div>
      )}
    </div>
  );
}
