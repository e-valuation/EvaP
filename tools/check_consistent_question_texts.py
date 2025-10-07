#!/usr/bin/env python3
import os
import sys
from collections import Counter

import django
from django.conf import settings

_stdout = sys.stdout


assert not settings.configured
os.environ.setdefault("DJANGO_SETTINGS_MODULE", "evap.settings")
django.setup()
from evap.evaluation.models import Question  # noqa: E402

texts_de, texts_en = zip(*Question.objects.values_list("text_de", "text_en").distinct(), strict=True)

print("text_en collisions with same text_de:", file=_stdout)
collisions = {text for (text, count) in Counter(texts_de).items() if count > 1}
for collision in collisions:
    print(
        "\n".join(map(str, Question.objects.filter(text_de=collision).values("id", "text_de", "text_en"))), file=_stdout
    )
    print(file=_stdout)
print(file=_stdout)

print("text_de collisions with same text_en:", file=_stdout)
collisions = {text for (text, count) in Counter(texts_en).items() if count > 1}
for collision in collisions:
    print(
        "\n".join(map(str, Question.objects.filter(text_en=collision).values("id", "text_de", "text_en"))), file=_stdout
    )
    print(file=_stdout)
