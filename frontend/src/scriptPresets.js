import S15_SCRIPTS from './s15_01_20.md?raw';

const S15_SERIES_ID = 'shohizei_yami_s15';
const S15_SERIES_LABEL = '消費税の闇 S15';

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
    .trim() || `S15-${number}`;
}

function parseS15ShortPresets(md) {
  const headingPattern = /^##\s+S15-(\d{2})([^\r\n]*)$/gm;
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
      id: `${S15_SERIES_ID}_short_${number}`,
      label: `${S15_SERIES_LABEL}・ショート #${number}：${title}`,
      title: `${S15_SERIES_LABEL}｜#${number}｜${title}`,
      prompt: `${S15_SERIES_LABEL} #${number}「${title}」。給与明細の税と社会保険料を、台本指定に沿って解説するショート。`,
      format: 'short_vertical',
      duration: 60,
      // 図解はローカル生成。start_frame 指定シーンだけ外部の画像→動画生成を使う。
      model: 'google_omni',
      start_frame_engine_overrides: Object.fromEntries(
        script.split('\n\n').flatMap((block, index) =>
          block.includes('[start_frame:') ? [[index + 1, 'google_omni']] : []),
      ),
      tts_engine: 'stylebertvits2',
      bgm: true,
      bgm_auto: true,
      logo_filename: '消費税の闇新ヘッダー.jpg',
      subtitle_position_from_bottom_pct: 24,
      analystk_lipsync_source_mode: 'video',
      analystk_lipsync_source_set: 'real',
      analystk_lipsync_display_mode: 'full',
      short_timing_mode: 'script',
      standard_timing_mode: 'script_unbounded',
      final_call_text: '',
      final_call_speech: '',
      script,
    });
  });

  return presets;
}

const s15PresetMap = new Map();
parseS15ShortPresets(S15_SCRIPTS).forEach(preset => {
  s15PresetMap.set(preset.id, preset);
});

export const SCRIPT_PRESETS = Array.from(s15PresetMap.values())
  .sort((left, right) => left.id.localeCompare(right.id));

export const DEFAULT_SCRIPT_PRESET_ID = SCRIPT_PRESETS[0]?.id || 'custom';
