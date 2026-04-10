"""Genre-appropriate music generation prompts for ACE-Step, MusicGen, and Suno."""

# ACE-Step styles — each is a dict with id, label, and generation parameters
ACE_STEP_STYLES = [
    {
        "id": "chill_lofi",
        "label": "Chill Lo-Fi Beats",
        "genre": "lo-fi",
        "prompt": "lo-fi hip hop beats, vinyl crackle, mellow piano chords, relaxing study music",
        "tags": "lo-fi, chill, study",
    },
    {
        "id": "smooth_jazz",
        "label": "Smooth Jazz",
        "genre": "jazz",
        "prompt": "smooth jazz saxophone and piano, warm bass, brushed drums, evening lounge atmosphere",
        "tags": "jazz, smooth, saxophone",
    },
    {
        "id": "ambient_nature",
        "label": "Ambient Nature",
        "genre": "ambient",
        "prompt": "ambient atmospheric pads, gentle nature sounds, ethereal textures, meditation music",
        "tags": "ambient, nature, meditation",
    },
    {
        "id": "classical_piano",
        "label": "Classical Piano",
        "genre": "classical",
        "prompt": "classical piano solo, romantic era style, expressive dynamics, Chopin-like nocturne",
        "tags": "classical, piano, romantic",
    },
    {
        "id": "acoustic_guitar",
        "label": "Acoustic Guitar",
        "genre": "acoustic",
        "prompt": "fingerstyle acoustic guitar, warm and intimate, folk-inspired instrumental",
        "tags": "acoustic, guitar, folk",
    },
    {
        "id": "electronic_chill",
        "label": "Electronic Chill",
        "genre": "electronic",
        "prompt": "chillwave electronic, soft synth pads, downtempo beats, dreamy atmosphere",
        "tags": "electronic, chill, synth",
    },
    {
        "id": "orchestral_cinematic",
        "label": "Cinematic Orchestral",
        "genre": "instrumental",
        "prompt": "cinematic orchestral score, sweeping strings, gentle brass, inspiring and uplifting",
        "tags": "orchestral, cinematic, epic",
    },
    {
        "id": "bossa_nova",
        "label": "Bossa Nova",
        "genre": "jazz",
        "prompt": "bossa nova guitar and piano, gentle percussion, Brazilian jazz, warm and relaxing",
        "tags": "bossa nova, brazilian, jazz",
    },
    {
        "id": "piano_covers",
        "label": "Piano Pop Covers",
        "genre": "pop-covers",
        "prompt": "beautiful piano arrangement of popular songs, emotional and expressive, cover version",
        "tags": "piano, pop, covers",
    },
    {
        "id": "celtic_folk",
        "label": "Celtic Folk",
        "genre": "acoustic",
        "prompt": "celtic folk instrumental, fiddle and acoustic guitar, Irish-inspired, gentle and warm",
        "tags": "celtic, folk, fiddle",
    },
]

# MusicGen styles
MUSICGEN_STYLES = [
    {
        "id": "lofi_study",
        "label": "Lo-Fi Study Session",
        "genre": "lo-fi",
        "prompt": "lo-fi hip hop beats for studying, mellow piano chords, vinyl crackle, tape hiss, relaxing",
    },
    {
        "id": "jazz_cafe",
        "label": "Jazz Cafe",
        "genre": "jazz",
        "prompt": "smooth jazz cafe music, soft piano, upright bass, brushed drums, warm and cozy",
    },
    {
        "id": "ambient_space",
        "label": "Ambient Space",
        "genre": "ambient",
        "prompt": "ambient space music, deep reverb pads, slowly evolving textures, cosmic and peaceful",
    },
    {
        "id": "classical_strings",
        "label": "Classical Strings",
        "genre": "classical",
        "prompt": "classical string quartet, elegant and refined, baroque-inspired, chamber music",
    },
    {
        "id": "indie_acoustic",
        "label": "Indie Acoustic",
        "genre": "acoustic",
        "prompt": "indie acoustic instrumental, fingerpicked guitar, gentle ukulele, warm and hopeful",
    },
    {
        "id": "synthwave_soft",
        "label": "Soft Synthwave",
        "genre": "electronic",
        "prompt": "soft synthwave, retro 80s synths, dreamy arpeggios, nostalgic and mellow",
    },
    {
        "id": "world_instrumental",
        "label": "World Instrumental",
        "genre": "instrumental",
        "prompt": "world music instrumental, sitar, kalimba, gentle percussion, cultural fusion, relaxing",
    },
    {
        "id": "pop_piano",
        "label": "Pop Piano Covers",
        "genre": "pop-covers",
        "prompt": "piano cover of popular hit song, emotional arrangement, beautiful and expressive",
    },
]

# Suno styles
SUNO_STYLES = [
    {
        "id": "lofi_beats",
        "title": "Lo-Fi Chill Beats",
        "genre": "lo-fi",
        "style": "lo-fi hip hop",
        "prompt": "Relaxing lo-fi hip hop instrumental with vinyl crackle, soft piano, and mellow beats",
    },
    {
        "id": "jazz_evening",
        "title": "Jazz Evening",
        "genre": "jazz",
        "style": "smooth jazz",
        "prompt": "Smooth jazz instrumental, saxophone lead, piano comping, walking bass, evening vibes",
    },
    {
        "id": "ambient_dreams",
        "title": "Ambient Dreams",
        "genre": "ambient",
        "style": "ambient",
        "prompt": "Ethereal ambient soundscape, slowly evolving pads, gentle chimes, deep space atmosphere",
    },
    {
        "id": "classical_nocturne",
        "title": "Classical Nocturne",
        "genre": "classical",
        "style": "classical piano",
        "prompt": "Classical piano nocturne, Chopin-inspired, expressive and emotional, solo piano",
    },
    {
        "id": "acoustic_campfire",
        "title": "Acoustic Campfire",
        "genre": "acoustic",
        "style": "acoustic folk",
        "prompt": "Acoustic guitar campfire instrumental, warm fingerpicking, gentle strumming, nature vibes",
    },
    {
        "id": "electronic_sunset",
        "title": "Electronic Sunset",
        "genre": "electronic",
        "style": "chillwave",
        "prompt": "Chillwave electronic instrumental, warm synth pads, sunset vibes, downtempo groove",
    },
    {
        "id": "cinematic_journey",
        "title": "Cinematic Journey",
        "genre": "instrumental",
        "style": "cinematic orchestral",
        "prompt": "Epic cinematic orchestral instrumental, sweeping strings, gentle piano, inspiring journey",
    },
    {
        "id": "pop_acoustic_cover",
        "title": "Pop Acoustic Cover",
        "genre": "pop-covers",
        "style": "acoustic pop cover",
        "prompt": "Acoustic guitar cover of a popular song, stripped-back arrangement, emotional vocal melody on guitar",
    },
]


def get_styles_for_generator(generator):
    """Return style list for a given generator."""
    if generator == "ace_step":
        return ACE_STEP_STYLES
    elif generator == "musicgen":
        return MUSICGEN_STYLES
    elif generator == "suno":
        return SUNO_STYLES
    return []


def get_style(generator, style_id):
    """Look up a specific style by generator and ID."""
    styles = get_styles_for_generator(generator)
    return next((s for s in styles if s["id"] == style_id), None)
