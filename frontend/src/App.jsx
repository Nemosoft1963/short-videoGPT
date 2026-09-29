import React, { useEffect, useState } from 'react';
import { createRoot } from 'react-dom/client';
import { Film, Download, FileText, RefreshCw, Play, Square, Image as ImageIcon, Trash2 } from 'lucide-react';
import './style.css';
import { DEFAULT_SCRIPT_PRESET_ID, SCRIPT_PRESETS } from './scriptPresets';

const API_BASE = import.meta.env.VITE_API_BASE || '';
const DURATION_OPTIONS = {
  short_vertical: [
    { value: 15, label: '15秒' },
    { value: 30, label: '30秒' },
    { value: 60, label: '60秒' },
  ],
  standard_landscape: [
    { value: 60, label: '1分' },
    { value: 180, label: '3分' },
    { value: 300, label: '5分' },
    { value: 600, label: '10分' },
  ],
};

const DEFAULT_SCRIPT_PRESET = SCRIPT_PRESETS.find(x => x.id === DEFAULT_SCRIPT_PRESET_ID) || SCRIPT_PRESETS[0];

function App() {
  const [scriptPresetId, setScriptPresetId] = useState(DEFAULT_SCRIPT_PRESET_ID);
  const [form, setForm] = useState({
    title: DEFAULT_SCRIPT_PRESET.title,
    prompt: DEFAULT_SCRIPT_PRESET.prompt,
    script: DEFAULT_SCRIPT_PRESET.script,
    format: DEFAULT_SCRIPT_PRESET.format || 'short_vertical',
    duration: DEFAULT_SCRIPT_PRESET.duration || 60,
    short_timing_mode: DEFAULT_SCRIPT_PRESET.short_timing_mode || 'script',
    standard_timing_mode: DEFAULT_SCRIPT_PRESET.standard_timing_mode || 'script_unbounded',
    style: 'serious_documentary',
    model: DEFAULT_SCRIPT_PRESET.model || 'mock',
    tts_engine: 'qwen3tts',
    voice_speaker_id: 0,
    voice_speed_scale: 1.0,
    tts_model_id: 3,
    tts_style: 'Neutral',
    tts_style_weight: 1.0,
    tts_sdp_ratio: 0.2,
    tts_noise: 0.6,
    tts_noisew: 0.8,
    tts_language: 'JP',
    qwen3_tts_model: 'Qwen/Qwen3-TTS-12Hz-0.6B-Base',
    qwen3_tts_mode: 'voice_clone',
    qwen3_tts_speaker: 'chikamichi',
    qwen3_tts_instruct: '',
    analystk_lipsync_source_mode: 'video',
    analystk_lipsync_source_set: 'anime',
    analystk_lipsync_display_mode: 'bottom',
    subtitle: true,
    subtitle_font_size: 72,
    subtitle_wrap_chars: 14,
    subtitle_max_lines: 3,
    subtitle_position_from_bottom_pct: 40,
    head_title: '',
    thumbnail_time_seconds: 0,
    final_call_text: DEFAULT_SCRIPT_PRESET.format === 'standard_landscape' ? 'チャンネル登録よろしくね' : '',
    final_call_speech: DEFAULT_SCRIPT_PRESET.format === 'standard_landscape' ? 'チャンネル登録よろしくね' : '',
    narration_volume: 1.0,
    bgm: false,
    bgm_filename: '',
    logo_filename: '',
    background_video_filename: '',
    intro_video_filename: '',
    outro_video_filename: '',
    typewriter_subtitle: true,
    bgm_auto: true,
  });
  const [voices, setVoices] = useState([]);
  const [voiceSource, setVoiceSource] = useState('');
  const [stylesByModel, setStylesByModel] = useState({});
  const [logos, setLogos] = useState([]);
  const [bgms, setBgms] = useState([]);
  const [bumpers, setBumpers] = useState([]);
  const [projectId, setProjectId] = useState('');
  const [status, setStatus] = useState(null);
  const [projects, setProjects] = useState([]);
  const [busy, setBusy] = useState(false);
  const [thumbVersion, setThumbVersion] = useState(0);
  const [diagnostics, setDiagnostics] = useState(null);
  const [apiError, setApiError] = useState('');

  const update = (key, value) => setForm(prev => ({ ...prev, [key]: value }));
  const updateManual = (key, value) => {
    setScriptPresetId('custom');
    update(key, value);
  };
  const updateFormat = (format) => setForm(prev => ({
    ...prev,
    format,
    duration: format === 'standard_landscape' ? 600 : 60,
    standard_timing_mode: format === 'standard_landscape' ? 'script_unbounded' : 'duration_min',
    subtitle_position_from_bottom_pct: format === 'standard_landscape' ? 40 : prev.subtitle_position_from_bottom_pct,
    head_title: format === 'standard_landscape' && !prev.head_title ? prev.title : prev.head_title,
    ...(format === 'short_vertical' ? { final_call_text: '', final_call_speech: '' } : {}),
  }));

  function applyPreset(id) {
    const p = SCRIPT_PRESETS.find(x => x.id === id);
    if (!p) return;
    setScriptPresetId(id);
    setForm(prev => ({
      ...prev,
      title: p.title,
      prompt: p.prompt,
      script: p.script,
      head_title: p.title,
      ...(p.format ? { format: p.format } : {}),
      ...(p.duration ? { duration: p.duration } : {}),
      ...(p.short_timing_mode ? { short_timing_mode: p.short_timing_mode } : {}),
      ...((p.format || prev.format) === 'standard_landscape'
        ? { standard_timing_mode: 'script_unbounded' }
        : (p.standard_timing_mode ? { standard_timing_mode: p.standard_timing_mode } : {})),
      ...(p.model ? { model: p.model } : {}),
      ...(p.analystk_lipsync_source_mode ? { analystk_lipsync_source_mode: p.analystk_lipsync_source_mode } : {}),
      ...(p.analystk_lipsync_source_set ? { analystk_lipsync_source_set: p.analystk_lipsync_source_set } : {}),
      ...(p.analystk_lipsync_display_mode ? { analystk_lipsync_display_mode: p.analystk_lipsync_display_mode } : {}),
      ...('final_call_text' in p ? { final_call_text: p.final_call_text } : {}),
      ...('final_call_speech' in p ? { final_call_speech: p.final_call_speech } : {}),
      ...(p.format === 'standard_landscape' ? { subtitle_position_from_bottom_pct: 40 } : {}),
    }));
  }

  async function apiFetch(path, options = {}) {
    const url = `${API_BASE}${path}`;
    try {
      const res = await fetch(url, options);
      return res;
    } catch (e) {
      const hint = [
        `APIに接続できません: ${url}`,
        '確認: docker compose ps',
        '確認: http://localhost:3000/api/health',
        '確認: docker compose logs --tail=100 api',
        '確認: docker compose logs --tail=100 frontend',
      ].join('\n');
      throw new Error(`${e.message}\n${hint}`);
    }
  }

  async function fetchDiagnostics() {
    setApiError('');
    try {
      const res = await apiFetch('/api/diagnostics');
      if (!res.ok) {
        let detail = await res.text();
        try { detail = JSON.stringify(JSON.parse(detail), null, 2); } catch (_) {}
        throw new Error(detail);
      }
      setDiagnostics(await res.json());
    } catch (e) {
      setApiError(String(e));
    }
  }

  async function fetchVoices() {
    try {
      const res = await apiFetch('/api/voices');
      if (res.ok) {
        const data = await res.json();
        setVoices(data.voices || []);
        setVoiceSource(data.source || '');
        setStylesByModel(data.styles_by_model || {});
        const first = (data.voices || [])[0];
        if (data.source === 'stylebertvits2' && (data.default_model_id !== undefined || first?.model_id !== undefined)) {
          const modelId = Number(data.default_model_id ?? first.model_id);
          const styles = data.styles_by_model?.[String(modelId)] || [];
          const selectedVoice = (data.voices || []).find(v => Number(v.model_id) === modelId) || first;
          setForm(prev => ({
            ...prev,
            tts_engine: selectedVoice?.tts_engine || data.source || prev.tts_engine,
            tts_model_id: modelId,
            voice_speaker_id: Number(selectedVoice?.speaker_id ?? prev.voice_speaker_id),
            tts_style: styles.includes(data.default_style) ? data.default_style : (styles.includes(prev.tts_style) ? prev.tts_style : (styles[0] || 'Neutral')),
          }));
        }
        if ((data.source || '').startsWith('qwen3tts')) {
          setForm(prev => ({
            ...prev,
            tts_engine: first?.tts_engine || data.source || prev.tts_engine,
            voice_speaker_id: Number(first?.speaker_id ?? prev.voice_speaker_id ?? 0),
            qwen3_tts_speaker: first?.speaker || data.default_speaker || prev.qwen3_tts_speaker,
            qwen3_tts_model: first?.qwen3_tts_model || data.default_model || prev.qwen3_tts_model,
            qwen3_tts_mode: first?.qwen3_tts_mode || data.default_mode || prev.qwen3_tts_mode,
            qwen3_tts_instruct: data.default_instruct ?? prev.qwen3_tts_instruct,
            tts_language: data.default_language === 'English' ? 'EN' : (data.default_language === 'Chinese' ? 'ZH' : prev.tts_language),
          }));
        }
      }
    } catch (e) {
      setApiError(String(e));
    }
  }

  async function fetchLogos() {
    try {
      const res = await apiFetch('/api/assets/logos');
      if (res.ok) {
        const data = await res.json();
        setLogos(data.logos || []);
      }
    } catch (_) {}
  }

  async function fetchBumpers() {
    try {
      const res = await apiFetch('/api/assets/bumpers');
      if (res.ok) {
        const data = await res.json();
        setBumpers(data.bumpers || []);
      }
    } catch (_) {}
  }

  async function fetchBgms() {
    try {
      const res = await apiFetch('/api/assets/bgms');
      if (res.ok) {
        const data = await res.json();
        setBgms(data.bgms || []);
      }
    } catch (_) {}
  }

  async function uploadLogo(file) {
    const formData = new FormData();
    formData.append('file', file);
    try {
      const res = await apiFetch('/api/assets/logo', {
        method: 'POST',
        body: formData,
      });
      if (res.ok) {
        const data = await res.json();
        update('logo_filename', data.filename);
        alert(`ロゴをアップロードしました: ${data.filename}`);
      } else {
        alert('ロゴアップロードに失敗しました');
      }
    } catch (e) {
      alert(`ロゴアップロード失敗: ${e}`);
    }
  }

  async function uploadBumper(file, targetKey) {
    const formData = new FormData();
    const prefix = targetKey === 'intro_video_filename'
      ? 'intro'
      : (targetKey === 'outro_video_filename' ? 'outro' : 'background');
    formData.append('file', file, `${prefix}_${file.name}`);
    try {
      const res = await apiFetch('/api/assets/bumper', {
        method: 'POST',
        body: formData,
      });
      if (res.ok) {
        const data = await res.json();
        update(targetKey, data.filename);
        alert(`既成動画をアップロードしました: ${data.filename}`);
      } else {
        alert('既成動画アップロードに失敗しました');
      }
    } catch (e) {
      alert(`既成動画アップロード失敗: ${e}`);
    }
  }

  async function uploadBgm(file) {
    const formData = new FormData();
    formData.append('file', file);
    try {
      const res = await apiFetch('/api/assets/bgm', {
        method: 'POST',
        body: formData,
      });
      if (res.ok) {
        const data = await res.json();
        setForm(prev => ({ ...prev, bgm: true, bgm_auto: false, bgm_filename: data.filename }));
      } else {
        alert('BGMアップロードに失敗しました');
      }
    } catch (e) {
      alert(`BGMアップロードエラー: ${e}`);
    }
  }

  async function createProject() {
    setBusy(true);
    setStatus(null);
    try {
      const res = await apiFetch('/api/projects', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(form),
      });
      if (!res.ok) throw new Error(await res.text());
      const data = await res.json();
      setProjectId(data.project_id);
      await fetchStatus(data.project_id);
      await fetchProjects();
    } catch (e) {
      alert(`生成開始に失敗しました: ${e}`);
    } finally {
      setBusy(false);
    }
  }

  async function fetchStatus(id = projectId) {
    if (!id) return;
    try {
      const res = await apiFetch(`/api/projects/${id}/status`);
      if (res.ok) setStatus(await res.json());
    } catch (e) {
      setApiError(String(e));
    }
  }

  async function fetchProjects() {
    try {
      const res = await apiFetch('/api/projects');
      if (res.ok) {
        const data = await res.json();
        setProjects(data.projects || []);
      }
    } catch (e) {
      setApiError(String(e));
    }
  }

  useEffect(() => { fetchProjects(); fetchVoices(); fetchLogos(); fetchBgms(); fetchBumpers(); }, []);

  useEffect(() => {
    if (!projectId) return;
    const t = setInterval(() => fetchStatus(projectId), 3000);
    return () => clearInterval(t);
  }, [projectId]);

  const completed = status?.status === 'completed';
  const TERMINAL = new Set(['completed', 'failed', 'cancelled']);
  const isActive = status && !TERMINAL.has(status.status);
  const isStyleBert = voiceSource.startsWith('stylebertvits2');
  const isQwen3TTS = voiceSource.startsWith('qwen3tts');
  const supportsCharacterLipsync = isQwen3TTS || isStyleBert;
  const selectedVoiceValue = isStyleBert
    ? `${form.tts_model_id}:${form.voice_speaker_id}`
    : String(form.voice_speaker_id);
  const sbv2ModelOptions = voices
    .filter(v => v.model_id !== undefined)
    .filter((v, index, list) => list.findIndex(item => Number(item.model_id) === Number(v.model_id)) === index);

  async function cancelProject() {
    if (!projectId) return;
    if (!window.confirm('生成を中断しますか？')) return;
    try {
      const res = await apiFetch(`/api/projects/${projectId}/cancel`, { method: 'POST' });
      if (res.ok) await fetchStatus(projectId);
    } catch (e) {
      setApiError(String(e));
    }
  }

  async function deleteProject(id) {
    if (!id) return;
    if (!window.confirm(`履歴 ${id} を削除しますか？`)) return;
    try {
      const res = await apiFetch(`/api/projects/${id}`, { method: 'DELETE' });
      if (!res.ok) throw new Error(await res.text());
      if (projectId === id) {
        setProjectId('');
        setStatus(null);
      }
      await fetchProjects();
    } catch (e) {
      alert(`履歴削除に失敗しました: ${e}`);
    }
  }

  async function createThumbnail() {
    if (!status?.project_id) return;
    try {
      const qs = new URLSearchParams({ at_seconds: String(Number(form.thumbnail_time_seconds) || 0) });
      const res = await apiFetch(`/api/projects/${status.project_id}/thumbnail?${qs.toString()}`, { method: 'POST' });
      if (!res.ok) throw new Error(await res.text());
      setThumbVersion(v => v + 1);
      await fetchStatus(status.project_id);
    } catch (e) {
      setApiError(String(e));
    }
  }

  const headTitleCandidates = Array.from(new Set([
    form.title,
    form.prompt.split(/[。\n]/)[0],
    ...(form.script.match(/字幕[：:]\s*(.+)/g) || []).slice(0, 3).map(x => x.replace(/^字幕[：:]\s*/, '')),
    ...(form.script.match(/映像[：:]\s*\[graphic(?::[^\]]+)?\]\s*(.+)/g) || []).slice(0, 3).map(x => x.replace(/^映像[：:]\s*\[graphic(?::[^\]]+)?\]\s*/, '')),
  ].map(x => (x || '').replace(/\s+/g, ' ').trim()).filter(x => x && x.length <= 80))).slice(0, 8);

  return (
    <div className="app">
      <header className="header">
        <div className="brand"><Film size={28} /> Local Short Video Generator</div>
        <div className="sub">Docker / OSS / ローカル / 日本語ショート動画</div>
      </header>

      <main className="grid">
        <section className="card">
          <h2>新規ショート動画</h2>
          <label>タイトル</label>
          <input value={form.title} onChange={e => updateManual('title', e.target.value)} />

          <label>テーマ・主張</label>
          <textarea rows="4" value={form.prompt} onChange={e => updateManual('prompt', e.target.value)} />

          <label>台本プリセット（選択するとタイトル・テーマ・台本を一括セット）</label>
          <div className="presetRow">
            <select value={scriptPresetId} onChange={e => setScriptPresetId(e.target.value)}>
              <option value="custom">手入力 / 貼り付け</option>
              {SCRIPT_PRESETS.map(p => <option key={p.id} value={p.id}>{p.label}</option>)}
            </select>
            <button
              type="button"
              className="small"
              disabled={scriptPresetId === 'custom'}
              onClick={() => applyPreset(scriptPresetId)}
            >
              プリセット読込
            </button>
          </div>
          <p className="miniHint">選択だけでは本文を変更しません。読み込みボタンを押した時だけ、タイトル・テーマ・台本を置き換えます。</p>

          <label>台本（空行でシーン分割・音声と字幕に使用）</label>
          <textarea className="scriptBox" rows="14" value={form.script} onChange={e => updateManual('script', e.target.value)} />
          <div className="row">
            <div>
              <label>出力サイズ</label>
              <select value={form.format} onChange={e => updateFormat(e.target.value)}>
                <option value="short_vertical">ショート 1080x1920</option>
                <option value="standard_landscape">標準 1920x1080</option>
              </select>
              <p className="miniHint">{form.format === 'short_vertical' ? '縦型ショートとして生成します。' : '横型Full HDで、最長10分まで指定できます。'}</p>
            </div>
            {form.format === 'standard_landscape' && (
              <div>
                <label>標準動画の尺制御</label>
                <select value={form.standard_timing_mode} onChange={e => update('standard_timing_mode', e.target.value)}>
                  <option value="duration_min">指定尺以上に揃える（最大10分）</option>
                  <option value="script_unbounded">台本に合わせる（上限なし）</option>
                </select>
                <p className="miniHint">
                  {form.standard_timing_mode === 'script_unbounded'
                    ? '台本ブロック数と1シーン上限を外し、完成尺を台本合計に合わせます。'
                    : '指定した長さを下回らないように生成します。'}
                </p>
              </div>
            )}
            {form.format === 'standard_landscape' && form.standard_timing_mode !== 'script_unbounded' && (
              <div>
                <label>動画時間</label>
                <select value={form.duration} onChange={e => update('duration', Number(e.target.value))}>
                  {(DURATION_OPTIONS[form.format] || DURATION_OPTIONS.short_vertical).map(option => (
                    <option key={option.value} value={option.value}>{option.label}</option>
                  ))}
                </select>
                <p className="miniHint">標準動画の完成尺です。</p>
              </div>
            )}
            {form.format === 'short_vertical' && (
              <div>
                <label>ショート尺</label>
                <select value={form.short_timing_mode} onChange={e => update('short_timing_mode', e.target.value)}>
                  <option value="fixed_44">44秒固定</option>
                  <option value="fixed_57">57秒固定</option>
                  <option value="script">台本に合わせる</option>
                </select>
                <p className="miniHint">
                  {form.short_timing_mode === 'fixed_44'
                    ? '本編43秒 + 最後のタメ約1秒で44秒に揃えます。'
                    : form.short_timing_mode === 'fixed_57'
                      ? '本編56秒 + 最後のタメ約1秒で57秒に揃えます。'
                      : '時間指定は使わず、台本の内容から尺を決めて最後に約2.5秒のタメを残します。'}
                </p>
              </div>
            )}
          </div>
          <p className="hint">細かく指定する場合は「映像：」「ナレーション：」「字幕：」を各シーンに書けます。空欄にすると自動台本になります。</p>

          <div className="row single">
            <div>
              <label>スタイル</label>
              <select value={form.style} onChange={e => update('style', e.target.value)}>
                <option value="serious_documentary">硬質ドキュメンタリー</option>
                <option value="small_business_awareness">中小企業向け啓発</option>
                <option value="tax_issue">消費税問題提起</option>
                <option value="recruiting">採用ショート</option>
                <option value="product_intro">商品紹介</option>
              </select>
            </div>
          </div>

          <div className="row">
            <div>
              <label>動画生成モード</label>
              <select value={form.model} onChange={e => update('model', e.target.value)}>
                <option value="mock">MOC / mock ローカル確認</option>
                <option value="runway">RUNWAY 本番生成</option>
                <option value="luma">LUMA / Dream Machine 本番生成</option>
                <option value="veo_lite">Google Veo 3.1 Lite 本番生成</option>
                <option value="minimax">MiniMax Hailuo 本番生成</option>
              </select>
              <p className="miniHint">MOCはAPIを使わない確認用です。RUNWAY / LUMA / Veo Lite / MiniMaxはクレジットを消費する本番生成です。</p>
            </div>
            <div>
              <label>音声</label>
              <select value={selectedVoiceValue} onChange={e => {
                const value = e.target.value;
                const selected = isStyleBert
                  ? voices.find(v => `${v.model_id}:${v.speaker_id}` === value)
                  : voices.find(v => Number(v.speaker_id) === Number(value));
                const speakerId = Number(selected?.speaker_id ?? value);
                const modelId = selected?.model_id !== undefined ? Number(selected.model_id) : form.tts_model_id;
                const styles = stylesByModel[String(modelId)] || [];
                setForm(prev => ({
                  ...prev,
                  voice_speaker_id: speakerId,
                  tts_engine: selected?.tts_engine || voiceSource || prev.tts_engine,
                  tts_model_id: modelId,
                  tts_style: styles.includes(prev.tts_style) ? prev.tts_style : (styles[0] || prev.tts_style || 'Neutral'),
                  ...(isQwen3TTS ? {
                    qwen3_tts_speaker: selected?.speaker || prev.qwen3_tts_speaker,
                    qwen3_tts_model: selected?.qwen3_tts_model || prev.qwen3_tts_model,
                    qwen3_tts_mode: selected?.qwen3_tts_mode || prev.qwen3_tts_mode,
                    tts_language: selected?.qwen3_tts_language === 'English' ? 'EN' : (selected?.qwen3_tts_language === 'Chinese' ? 'ZH' : prev.tts_language),
                  } : {}),
                }));
              }}>
                {voices.length === 0 && <option value={0}>音声モデルを確認中</option>}
                {voices.map(v => {
                  const optionValue = v.model_id !== undefined ? `${v.model_id}:${v.speaker_id}` : String(v.speaker_id);
                  return <option key={`${v.model_id ?? 'default'}-${v.speaker_id}`} value={optionValue}>{v.name}（model:{v.model_id ?? '-'} / speaker:{v.speaker_id}）</option>;
                })}
              </select>
              <p className="miniHint">話者一覧: {voiceSource || 'loading'}</p>
            </div>
          </div>

          {isStyleBert && (
            <div className="row">
              <div>
                <label>SBV2 音声モデル</label>
                <select
                  value={form.tts_model_id}
                  onChange={e => {
                    const modelId = Number(e.target.value);
                    const styles = stylesByModel[String(modelId)] || [];
                    const selected = voices.find(v => Number(v.model_id) === modelId);
                    setForm(prev => ({
                      ...prev,
                      tts_model_id: modelId,
                      tts_engine: selected?.tts_engine || voiceSource || prev.tts_engine,
                      voice_speaker_id: Number(selected?.speaker_id ?? prev.voice_speaker_id),
                      tts_style: styles.includes(prev.tts_style) ? prev.tts_style : (styles[0] || prev.tts_style || 'Neutral'),
                    }));
                  }}
                >
                  {sbv2ModelOptions.map(v => (
                    <option key={v.model_id} value={v.model_id}>{v.name.replace(/^SBV2 model \d+ \/ /, '')}（model:{v.model_id}）</option>
                  ))}
                </select>
              </div>
              <div>
                <label>SBV2 スタイル</label>
                <select value={form.tts_style} onChange={e => update('tts_style', e.target.value)}>
                  {(stylesByModel[String(form.tts_model_id)] || [form.tts_style || 'Neutral']).map(style => (
                    <option key={style} value={style}>{style}</option>
                  ))}
                </select>
              </div>
            </div>
          )}

          {isQwen3TTS && (
            <div className="row">
              <div>
                <label>Qwen3-TTS モデル</label>
                <input value={form.qwen3_tts_model} onChange={e => update('qwen3_tts_model', e.target.value)} />
                <p className="miniHint">例: Qwen/Qwen3-TTS-12Hz-0.6B-CustomVoice</p>
              </div>
              <div>
                <label>近道君 音声プロファイル</label>
                <input value={form.qwen3_tts_speaker} onChange={e => update('qwen3_tts_speaker', e.target.value)} />
                <p className="miniHint">Qwen3-TTSサーバー側に作成したクローン名を指定します。</p>
              </div>
            </div>
          )}

          {isQwen3TTS && (
            <div className="row">
              <div>
                <label>Qwen3-TTS モード</label>
                <select value={form.qwen3_tts_mode} onChange={e => update('qwen3_tts_mode', e.target.value)}>
                  <option value="custom_voice">CustomVoice</option>
                  <option value="voice_clone">Voice Clone</option>
                  <option value="voice_design">Voice Design</option>
                </select>
              </div>
              <div>
                <label>Qwen3-TTS 言語</label>
                <select value={form.tts_language} onChange={e => update('tts_language', e.target.value)}>
                  <option value="JP">Japanese</option>
                  <option value="EN">English</option>
                  <option value="ZH">Chinese</option>
                </select>
              </div>
            </div>
          )}

          {isQwen3TTS && (
            <div className="row single">
              <div>
                <label>近道君 音声指示</label>
                <textarea rows="3" value={form.qwen3_tts_instruct} onChange={e => update('qwen3_tts_instruct', e.target.value)} />
                <p className="miniHint">空欄ならサーバー側の既定設定を使います。声質・感情・話速の指示を入れられます。</p>
              </div>
            </div>
          )}

          {supportsCharacterLipsync && (
            <div className="row">
              <div>
                <label>分析官K／少佐 口パクセット</label>
                <select value={form.analystk_lipsync_source_set} onChange={e => update('analystk_lipsync_source_set', e.target.value)}>
                  <option value="anime">アニメセット</option>
                  <option value="real">リアルセット</option>
                </select>
                <p className="miniHint">分析官Kまたは少佐が話すシーンに使う口パク元素材のセットを選びます。</p>
              </div>
              <div>
                <label>分析官K／少佐 口パク素材</label>
                <select value={form.analystk_lipsync_source_mode} onChange={e => update('analystk_lipsync_source_mode', e.target.value)}>
                  <option value="image">静止画を使う</option>
                  <option value="video">動画を使う</option>
                  <option value="auto">自動選択</option>
                </select>
                <p className="miniHint">セット内の静止画・動画を選びます。リアルセットは動画素材を登録済みです。</p>
              </div>
            </div>
          )}

          {supportsCharacterLipsync && (
            <div className="row">
              <div>
                <label>分析官K／少佐 表示方法</label>
                <select value={form.analystk_lipsync_display_mode} onChange={e => update('analystk_lipsync_display_mode', e.target.value)}>
                  <option value="bottom">下側に重ねる</option>
                  <option value="full">シーン全体に表示</option>
                  <option value="explain_right">解説スタイル：右側に話者／左側に字幕</option>
                </select>
                <p className="miniHint">解説スタイルは標準長尺専用です。分析官Kまたは少佐を右側に配置し、字幕を左側へ表示します。</p>
              </div>
              <div className="miniPanel">
                <strong>登録済み素材</strong>
                <p>アニメ静止画: analystk_lipsync_source.png</p>
                <p>アニメ動画: analystk_lipsync_source.mp4</p>
                <p>リアル動画: analystk_lipsync_real_source.mp4</p>
              </div>
            </div>
          )}

          <div className="row">
            <div>
              <label>音声速度 {form.voice_speed_scale.toFixed(2)}</label>
              <input type="range" min="0.85" max="1.30" step="0.01" value={form.voice_speed_scale} onChange={e => update('voice_speed_scale', Number(e.target.value))} />
              <p className="miniHint">推奨: 1.05〜1.15。さらに各シーン尺に合わせて自動補正します。</p>
            </div>
            <div>
              <label>ナレーション音量 {form.narration_volume.toFixed(2)}</label>
              <input type="range" min="0.3" max="2.0" step="0.05" value={form.narration_volume} onChange={e => update('narration_volume', Number(e.target.value))} />
              <p className="miniHint">標準: 1.0。BGM使用時は 1.2〜1.5 推奨。</p>
            </div>
            <div>
              <label>字幕サイズ</label>
              <select value={form.subtitle_font_size} onChange={e => update('subtitle_font_size', Number(e.target.value))}>
                <option value={60}>標準 60</option>
                <option value={72}>大きめ 72</option>
                <option value={84}>特大 84</option>
                <option value={96}>最大 96</option>
              </select>
            </div>
          </div>

          {voiceSource.startsWith('stylebertvits2') && (
            <div className="row">
              <div>
                <label>スタイル強度 {form.tts_style_weight.toFixed(2)}</label>
                <input type="range" min="0" max="3" step="0.05" value={form.tts_style_weight} onChange={e => update('tts_style_weight', Number(e.target.value))} />
              </div>
              <div>
                <label>SDP比率 {form.tts_sdp_ratio.toFixed(2)}</label>
                <input type="range" min="0" max="1" step="0.05" value={form.tts_sdp_ratio} onChange={e => update('tts_sdp_ratio', Number(e.target.value))} />
              </div>
              <div>
                <label>ノイズ {form.tts_noise.toFixed(2)}</label>
                <input type="range" min="0" max="1.5" step="0.05" value={form.tts_noise} onChange={e => update('tts_noise', Number(e.target.value))} />
              </div>
            </div>
          )}

          <div className="row">
            <div>
              <label>字幕位置：下から {form.subtitle_position_from_bottom_pct}%</label>
              <input
                type="range"
                min="8"
                max="55"
                step="1"
                value={form.subtitle_position_from_bottom_pct}
                onChange={e => update('subtitle_position_from_bottom_pct', Number(e.target.value))}
              />
              <p className="miniHint">推奨: 40%。数値を大きくすると字幕は上に移動します。</p>
            </div>
            <div>
              <label>1行の文字数</label>
              <select value={form.subtitle_wrap_chars} onChange={e => update('subtitle_wrap_chars', Number(e.target.value))}>
                <option value={12}>短め 12文字</option>
                <option value={14}>標準 14文字</option>
                <option value={16}>長め 16文字</option>
                <option value={18}>かなり長め 18文字</option>
              </select>
              <p className="miniHint">はみ出る場合は 12〜14 にします。</p>
            </div>
          </div>

          <div className="row">
            <div>
              <label>同時表示する最大行数</label>
              <select value={form.subtitle_max_lines} onChange={e => update('subtitle_max_lines', Number(e.target.value))}>
                <option value={2}>2行</option>
                <option value={3}>3行</option>
                <option value={4}>4行</option>
              </select>
              <p className="miniHint">超えた分は、同じシーン内で分割表示します。</p>
            </div>
            <div className="miniPanel">
              <strong>字幕折り返し</strong>
              <p>文節・句読点を優先して自動改行します。</p>
              <p>日本語文字は後処理で焼き込みます。</p>
            </div>
          </div>

          <div className="row single">
            <div>
              <label>ヘッドタイトル（標準画面の冒頭3秒）</label>
              <p className="miniHint"><strong>標準動画タイトル（冒頭3秒に表示）</strong></p>
              <select value="" onChange={e => e.target.value && update('head_title', e.target.value)}>
                <option value="">候補から選択</option>
                {headTitleCandidates.map(v => <option key={v} value={v}>{v}</option>)}
              </select>
              <input
                style={{marginTop:'8px'}}
                value={form.head_title}
                onChange={e => update('head_title', e.target.value)}
                placeholder="直接入力もできます"
              />
              <div style={{display:'flex', gap:'8px', flexWrap:'wrap', marginTop:'8px'}}>
                <button className="small" onClick={() => update('head_title', form.title)}>作品タイトルを使う</button>
                <button className="small" onClick={() => update('head_title', '')}>表示しない</button>
              </div>
              <p className="miniHint">標準 1920x1080 の完成動画冒頭に表示されます。空欄ならタイトル表示をスキップします。</p>
              <p className="miniHint">標準画面生成時、完成動画の最初の3秒だけ上部に表示します。空欄なら表示しません。</p>
            </div>
          </div>

          <div className="row">
            <div>
              <label>サムネ切り出し位置（秒）</label>
              <input
                type="number"
                min="0"
                step="0.1"
                value={form.thumbnail_time_seconds}
                onChange={e => update('thumbnail_time_seconds', Number(e.target.value))}
              />
              <p className="miniHint">0秒なら最初の画面からサムネイルを生成します。完成後にも再切り出しできます。</p>
            </div>
            <div className="miniPanel">
              <strong>サムネ画像</strong>
              <p>完成時にJPEGを自動生成します。時間指定で後から作り直せます。</p>
            </div>
          </div>

          <div className="row">
            <div>
              <label>最終コール：文字表示</label>
              <input
                value={form.final_call_text}
                onChange={e => update('final_call_text', e.target.value)}
                placeholder="例：チャンネル登録よろしくね"
              />
              <p className="miniHint">{form.format === 'short_vertical' ? 'ショートでは最終コールを追加しません。' : '完成動画の最後に追加します。空欄なら最終コールなしです。'}</p>
            </div>
            <div>
              <label>最終コール：GMN発話</label>
              <input
                value={form.final_call_speech}
                onChange={e => update('final_call_speech', e.target.value)}
                placeholder="例：チャンネル登録、よろしくね。"
              />
              <p className="miniHint">{form.format === 'short_vertical' ? '標準動画に切り替えた時だけ使用します。' : '同じ文字・発話・解像度なら管理済み成果物を再利用します。'}</p>
            </div>
          </div>

          <div className="row">
            <div className="checks">
              <label className="check"><input type="checkbox" checked={form.subtitle} onChange={e => update('subtitle', e.target.checked)} /> 字幕あり</label>
              <label className="check"><input type="checkbox" checked={form.typewriter_subtitle} onChange={e => update('typewriter_subtitle', e.target.checked)} /> タイプライター字幕</label>
              <label className="check"><input type="checkbox" checked={form.bgm} onChange={e => update('bgm', e.target.checked)} /> BGMあり</label>
              <label className="check"><input type="checkbox" checked={form.bgm_auto} onChange={e => update('bgm_auto', e.target.checked)} /> BGM自動選択</label>
            </div>
          </div>

          <div className="row single">
            <div>
              <label>BGM選択</label>
              <div style={{display:'flex', gap:'8px', alignItems:'center', flexWrap:'wrap'}}>
                <select
                  value={form.bgm_filename}
                  onChange={e => {
                    const filename = e.target.value;
                    setForm(prev => ({
                      ...prev,
                      bgm: filename ? true : prev.bgm,
                      bgm_auto: filename ? false : prev.bgm_auto,
                      bgm_filename: filename,
                    }));
                  }}
                  style={{flex:'1', minWidth:'180px'}}
                >
                  <option value="">（選択BGMなし）</option>
                  {bgms.map(b => <option key={b} value={b}>{b}</option>)}
                </select>
                <label className="small uploadButton">
                  ＋ BGMアップロード
                  <input
                    type="file"
                    accept="audio/mpeg,audio/wav,audio/x-wav,audio/mp4,audio/aac,audio/ogg,audio/flac"
                    style={{display:'none'}}
                    onChange={async e => {
                      if (e.target.files[0]) {
                        await uploadBgm(e.target.files[0]);
                        await fetchBgms();
                      }
                    }}
                  />
                </label>
              </div>
              {form.bgm_filename && (
                <p className="miniHint">選択中: {form.bgm_filename}
                  <button className="small" onClick={() => update('bgm_filename', '')} style={{marginLeft:'8px'}}>解除</button>
                </p>
              )}
              <p className="miniHint">BGMを選択すると自動選択はOFFになります。台本では [bgm:ファイル名] を映像指示と同じ行に書くとシーンごとに切り替えられます。</p>
            </div>
          </div>

          <div className="row">
            <div>
              <label>ロゴ画像（動画上部に表示）</label>
              <div style={{display:'flex', gap:'8px', alignItems:'center', flexWrap:'wrap'}}>
                <select
                  value={form.logo_filename}
                  onChange={e => update('logo_filename', e.target.value)}
                  style={{flex:'1', minWidth:'160px'}}
                >
                  <option value="">（ロゴなし）</option>
                  {logos.map(l => <option key={l} value={l}>{l}</option>)}
                </select>
                <label className="small" style={{cursor:'pointer', whiteSpace:'nowrap'}}>
                  ＋ 新規アップロード
                  <input
                    type="file"
                    accept="image/png,image/jpeg,image/gif,image/webp"
                    style={{display:'none'}}
                    onChange={async e => {
                      if (e.target.files[0]) {
                        await uploadLogo(e.target.files[0]);
                        await fetchLogos();
                      }
                    }}
                  />
                </label>
              </div>
              {form.logo_filename && (
                <p className="miniHint">✅ 選択中: {form.logo_filename}
                  <button className="small" onClick={() => update('logo_filename', '')} style={{marginLeft:'8px'}}>解除</button>
                </p>
              )}
              <p className="miniHint">PNG推奨。透過PNG対応。上部中央に自動配置します。</p>
            </div>
          </div>

          <div className="row single bumperList">
            <div>
              <label>本編背景動画（グラフィック / MOC 用）</label>
              <div className="bumperControl">
                <select
                  value={form.background_video_filename}
                  onChange={e => update('background_video_filename', e.target.value)}
                >
                  <option value="">（背景動画なし）</option>
                  {bumpers.map(v => <option key={v} value={v}>{v}</option>)}
                </select>
                <label className="small uploadButton">
                  ＋ 背景動画アップロード
                  <input
                    type="file"
                    accept="video/mp4,video/quicktime,video/webm"
                    style={{display:'none'}}
                    onChange={async e => {
                      if (e.target.files[0]) {
                        await uploadBumper(e.target.files[0], 'background_video_filename');
                        await fetchBumpers();
                      }
                    }}
                  />
                </label>
              </div>
              {form.background_video_filename && (
                <p className="miniHint">選択中: {form.background_video_filename}
                  <button className="small" onClick={() => update('background_video_filename', '')} style={{marginLeft:'8px'}}>解除</button>
                </p>
              )}
              <p className="miniHint">RUNWAY生成シーンではなく、[graphic:*] やMOCの本編シーンの下地としてループ使用します。</p>
            </div>
          </div>

          <div className="row single bumperList">
            <div>
              <label>前動画（生成動画の前に連結）</label>
              <div className="bumperControl">
                <select
                  value={form.intro_video_filename}
                  onChange={e => update('intro_video_filename', e.target.value)}
                >
                  <option value="">（前動画なし）</option>
                  {bumpers.map(v => <option key={v} value={v}>{v}</option>)}
                </select>
                <label className="small uploadButton">
                  ＋ 動画アップロード
                  <input
                    type="file"
                    accept="video/mp4,video/quicktime,video/webm"
                    style={{display:'none'}}
                    onChange={async e => {
                      if (e.target.files[0]) {
                        await uploadBumper(e.target.files[0], 'intro_video_filename');
                        await fetchBumpers();
                      }
                    }}
                  />
                </label>
              </div>
              {form.intro_video_filename && (
                <p className="miniHint">選択中: {form.intro_video_filename}
                  <button className="small" onClick={() => update('intro_video_filename', '')} style={{marginLeft:'8px'}}>解除</button>
                </p>
              )}
            </div>
            <div>
              <label>後動画（生成動画の後に連結）</label>
              <div className="bumperControl">
                <select
                  value={form.outro_video_filename}
                  onChange={e => update('outro_video_filename', e.target.value)}
                >
                  <option value="">（後動画なし）</option>
                  {bumpers.map(v => <option key={v} value={v}>{v}</option>)}
                </select>
                <label className="small uploadButton">
                  ＋ 動画アップロード
                  <input
                    type="file"
                    accept="video/mp4,video/quicktime,video/webm"
                    style={{display:'none'}}
                    onChange={async e => {
                      if (e.target.files[0]) {
                        await uploadBumper(e.target.files[0], 'outro_video_filename');
                        await fetchBumpers();
                      }
                    }}
                  />
                </label>
              </div>
              {form.outro_video_filename && (
                <p className="miniHint">選択中: {form.outro_video_filename}
                  <button className="small" onClick={() => update('outro_video_filename', '')} style={{marginLeft:'8px'}}>解除</button>
                </p>
              )}
              <p className="miniHint">完成時に「前動画＋生成動画＋後動画」の順で連結します。解像度は出力形式に合わせて自動調整します。</p>
            </div>
          </div>

          <button className="primary" onClick={createProject} disabled={busy}>
            <Play size={18} /> {busy ? '登録中...' : '生成開始'}
          </button>
          <p className="hint">映像生成モードで MOC / RUNWAY / LUMA を切り替えます。[graphic:*] はローカル合成、通常の映像プロンプトは選択中の生成モードで処理します。<br/>台本タグ例: 「映像：」「ナレーション：」「字幕：」「テキスト：上部に固定表示する文字列」「映像：[graphic:title] [bgm:serious_doc]」「映像：[motoko:fullscreen] [overlay:graphic:*] [graphic:bar_chart] 項目:値」など。テキスト：は通常映像シーンの上部に固定で焼き込まれます（複数行は改行で書けます）。</p>

          <div className="maintenanceArea">
            <h3>メンテナンス</h3>
            <p className="muted">生成開始で Failed to fetch が出る場合は、ここで接続状態を確認します。</p>
            <button className="secondary" onClick={fetchDiagnostics}><RefreshCw size={16} /> API診断</button>
            {apiError && <pre className="error">{apiError}</pre>}
            {diagnostics && <pre className="diag">{JSON.stringify(diagnostics, null, 2)}</pre>}
          </div>
        </section>

        <section className="card">
          <div style={{display:'flex', justifyContent:'space-between', alignItems:'center', gap:'12px', flexWrap:'wrap'}}>
            <h2 style={{margin:0}}>生成状況</h2>
            <button className="primary" onClick={createProject} disabled={busy}>
              <Play size={18} /> {busy ? '登録中...' : '生成開始'}
            </button>
          </div>
          {!status ? <p className="muted">生成を開始すると進捗が表示されます。</p> : (
            <div>
              <div className="projectId">{status.project_id}</div>
              <div className="progress"><div style={{ width: `${status.progress || 0}%` }} /></div>
              <div className="statusLine">{status.status} / {status.progress}%</div>
              <p>{status.message}</p>
              {status.error && <pre className="error">{status.error}</pre>}
              <div style={{display:'flex', gap:'8px', flexWrap:'wrap'}}>
                <button className="secondary" onClick={() => fetchStatus()}><RefreshCw size={16} /> 更新</button>
                {isActive && (
                  <button className="danger" onClick={cancelProject}><Square size={16} /> 中断</button>
                )}
              </div>
              {completed && (
                <div className="resultActions">
                  <a className="download" href={`${API_BASE}/api/projects/${status.project_id}/download`}><Download size={16} /> MP4をダウンロード</a>
                  {status.chapters_url && (
                    <a className="download" href={`${API_BASE}${status.chapters_url}`}><FileText size={16} /> セクションをダウンロード</a>
                  )}
                  <div className="thumbnailBox">
                    <img
                      src={`${API_BASE}/api/projects/${status.project_id}/thumbnail?time=${Number(form.thumbnail_time_seconds) || 0}&v=${thumbVersion}`}
                      alt="生成サムネイル"
                    />
                    <div className="thumbnailControls">
                      <input
                        type="number"
                        min="0"
                        step="0.1"
                        value={form.thumbnail_time_seconds}
                        onChange={e => update('thumbnail_time_seconds', Number(e.target.value))}
                      />
                      <button className="secondary" onClick={createThumbnail}><ImageIcon size={16} /> サムネ再生成</button>
                    </div>
                  </div>
                </div>
              )}
            </div>
          )}
        </section>

        <section className="card wide">
          <h2>最近のプロジェクト</h2>
          <table>
            <thead><tr><th>作成ID</th><th>タイトル</th><th>状態</th><th>進捗</th><th></th></tr></thead>
            <tbody>
              {projects.map(p => (
                <tr key={p.project_id}>
                  <td>{p.project_id}</td>
                  <td>{p.title}</td>
                  <td>{p.status}</td>
                  <td>{p.progress}%</td>
                  <td>
                    <div className="historyActions">
                      <button className="small" onClick={() => { setProjectId(p.project_id); fetchStatus(p.project_id); }}>表示</button>
                      <button className="small danger" onClick={() => deleteProject(p.project_id)} title="履歴を削除">
                        <Trash2 size={14} /> 削除
                      </button>
                    </div>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </section>
      </main>
    </div>
  );
}

createRoot(document.getElementById('root')).render(<App />);

