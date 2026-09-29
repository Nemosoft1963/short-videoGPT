import S13_SCRIPTS from './s13_scripts_v2.md?raw';

const S13_SERIES_ID = 'shohizei_yami_s13_v2';
const S13_SERIES_LABEL = '消費税の闇 S13';

function extractSceneScript(md) {
  const body = md.split(/\r?\n(?=#\s+投稿運用メモ)/)[0];
  const lines = body.split(/\r?\n/);
  const scenes = [];
  let current = null;

  for (const line of lines) {
    const trimmed = line.trim();

    if (trimmed.startsWith('映像：')) {
      if (current?.length) scenes.push(current.join('\n').trim());
      current = [trimmed];
      continue;
    }

    if (!current) continue;
    if (!trimmed) continue;
    if (trimmed === '---') continue;
    if (trimmed.startsWith('#')) continue;
    if (trimmed.startsWith('```')) continue;
    if (/^\*\*.+\*\*/.test(trimmed)) continue;
    if (/^>\s*/.test(trimmed)) continue;

    current.push(trimmed);
  }

  if (current?.length) scenes.push(current.join('\n').trim());
  return scenes.join('\n\n');
}

function cleanTitle(rawTitle, number) {
  return (rawTitle || '')
    .replace(/^[\s（(【\["'「]+/, '')
    .replace(/[\s）)】\]"'」]+$/, '')
    .trim() || `S13-${number}`;
}

function parseS13ShortPresets(md) {
  const headingPattern = /^##\s+S13-(\d{2})([^\r\n]*)$/gm;
  const headings = Array.from(md.matchAll(headingPattern));
  const postMemo = md.search(/^#\s+投稿運用メモ/m);
  const presets = [];

  headings.forEach((match, index) => {
    const number = match[1];
    const title = cleanTitle(match[2], number);
    const sectionStart = match.index + match[0].length;
    const sectionEnd = headings[index + 1]?.index ?? (postMemo >= 0 ? postMemo : md.length);
    const section = md.slice(sectionStart, sectionEnd);
    const script = extractSceneScript(section);

    if (!script) return;

    presets.push({
      id: `${S13_SERIES_ID}_short_${number}`,
      label: `${S13_SERIES_LABEL}・ショート #${number}：${title}`,
      title: `${S13_SERIES_LABEL}｜#${number}｜${title}`,
      prompt: `${S13_SERIES_LABEL} #${number}「${title}」。あずかり金という虚構を一次資料と制度構造から検証するショート。台本指定どおりに生成する。`,
      format: 'short_vertical',
      duration: 60,
      // S13 は graphic タグを保持し、図解をローカル生成する。外部動画APIの大量消費を避ける。
      model: 'mock',
      analystk_lipsync_source_mode: 'video',
      analystk_lipsync_source_set: 'real',
      analystk_lipsync_display_mode: 'full',
      short_timing_mode: 'fixed_57',
      standard_timing_mode: 'script_unbounded',
      final_call_text: '',
      final_call_speech: '',
      script,
    });
  });

  return presets;
}

const s13PresetMap = new Map();
parseS13ShortPresets(S13_SCRIPTS).forEach(preset => {
  s13PresetMap.set(preset.id, preset);
});

export const SCRIPT_PRESETS = Array.from(s13PresetMap.values())
  .sort((left, right) => left.id.localeCompare(right.id));

export const DEFAULT_SCRIPT_PRESET_ID = SCRIPT_PRESETS[0]?.id || 'custom';
