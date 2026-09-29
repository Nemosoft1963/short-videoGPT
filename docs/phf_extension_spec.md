# PHF Extension Spec

PHF, Psychological Hook Flash, inserts a 0.7-second impact block into the script.
It is intended for moments where viewer attention may drop.

## Tag

```text
[flash:Word:Runway prompt]
```

Example:

```text
映像：[graphic:talker_GPT]
GPT：社会保障のためという言葉を、信じてはいけません。
[flash:実は:Cinematic digital interference with red lightning]
GPT：その事実は、全く別の場所にあります。
```

## Output

Each flash block becomes a 0.7-second scene with three synchronized layers.

- Video layer: Runway source when `model=runway`; local glitch fallback otherwise.
- Text layer: the specified word is burned in as a large center flash.
- Audio layer: boom, high-frequency tone, and glitch noise are mixed as the scene audio.

## Asset Recycling

Finished flash visuals are cached under:

```text
storage/assets/flashes/
```

The cache key includes word, prompt, width, height, fps, duration, and PHF version.
If the same word and prompt are reused, the cached 0.7-second PHF asset is copied directly and Runway is skipped.

## Notes

- Runway may generate a clip longer than 0.7 seconds. The PHF pipeline normalizes the final flash asset to exactly 0.7 seconds.
- The flash scene has no narration subtitle. Its impact comes from the burned word and sound effect.
- When a flash appears between two dialogue lines in the same visual block, the following dialogue inherits the previous visual context.
