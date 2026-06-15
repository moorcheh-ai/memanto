# dataset.py

SHIFTING_PERSONA_DATASET = [
    {
        "session": 1,
        "role": "user",
        "content": "I am a huge fan of fast-paced action movies. I can't stand romance or slow dramas. They bore me to tears. Please remember this."
    },
    {
        "session": 2,
        "role": "user",
        "content": "I actually went on a date last night and we watched a romantic comedy. Surprisingly, it wasn't terrible. I still prefer action, but maybe a rom-com once in a while is okay if it has good pacing."
    },
    {
        "session": 3,
        "role": "user",
        "content": "Work has been really stressful lately. Honestly, I'm completely burnt out on loud action movies. I just want something relaxing right now. A slow, heartfelt romance or a deep drama sounds perfect."
    },
    {
        "session": 4,
        "role": "user",
        "content": "Can you recommend a movie for me to watch tonight based on my current preferences?"
    }
]

EXPECTED_STATE = "The user is currently burnt out on action movies due to stress and strongly prefers a relaxing, slow, heartfelt romance or deep drama for tonight."
