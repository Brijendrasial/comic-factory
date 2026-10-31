"""Expressive local character dialogue; no narrator substitution."""
def synthesize(c,data,folder,voice_model):
    from acting import synthesize as acted_speech
    return acted_speech(c,data,folder)
