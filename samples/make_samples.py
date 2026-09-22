"""Regenerate the sample text files.

    python samples/make_samples.py            -> samples/euc-kr.txt, samples/utf8.txt
    python samples/make_samples.py --big out.txt [--chapters 300] [--mb 10]

Both samples are public-domain works: poems by Kim Sowol (1902-1934) and the
opening of Lewis Carroll's "Alice's Adventures in Wonderland" (1865). The
--big file is synthetic and is not committed; it is for timing and for the
"300 chapters land in the NCX" check.
"""
from __future__ import annotations

import argparse
import os
import random

HERE = os.path.dirname(os.path.abspath(__file__))

KOREAN = """김소월 시선

이 파일은 EUC-KR(CP949)로 저장된 샘플입니다. 김소월(1902-1934)의 시는
저작권이 만료되어 누구나 자유롭게 쓸 수 있습니다. 시는 한 줄이 한 문단이므로
문단 처리를 "줄바꿈 기준"으로 두면 원문 그대로 살아납니다.


제1장 진달래꽃

나 보기가 역겨워
가실 때에는
말없이 고이 보내 드리우리다

영변에 약산
진달래꽃
아름 따다 가실 길에 뿌리우리다

가시는 걸음걸음
놓인 그 꽃을
사뿐히 즈려밟고 가시옵소서

나 보기가 역겨워
가실 때에는
죽어도 아니 눈물 흘리우리다


제2장 산유화

산에는 꽃 피네
꽃이 피네
갈 봄 여름 없이
꽃이 피네

산에
산에
피는 꽃은
저만치 혼자서 피어 있네

산에서 우는 작은 새여
꽃이 좋아
산에서
사노라네

산에는 꽃 지네
꽃이 지네
갈 봄 여름 없이
꽃이 지네


제3장 엄마야 누나야

엄마야 누나야 강변 살자
뜰에는 반짝이는 금모래빛
뒷문 밖에는 갈잎의 노래
엄마야 누나야 강변 살자


제4장 먼 후일

먼 훗날 당신이 찾으시면
그때에 내 말이 "잊었노라"

당신이 속으로 나무라면
"무척 그리다가 잊었노라"

그래도 당신이 나무라면
"믿기지 않아서 잊었노라"

오늘도 어제도 아니 잊고
먼 훗날 그때에 "잊었노라"
"""

ENGLISH = """Alice's Adventures in Wonderland
by Lewis Carroll

This sample is UTF-8 text with hard-wrapped lines and blank lines between
paragraphs, the way most Project Gutenberg files are laid out. Wrapped lines
are joined back into one paragraph; a blank line starts a new one.


CHAPTER I. Down the Rabbit-Hole

Alice was beginning to get very tired of sitting by her sister on the
bank, and of having nothing to do: once or twice she had peeped into the
book her sister was reading, but it had no pictures or conversations in
it, "and what is the use of a book," thought Alice "without pictures or
conversations?"

So she was considering in her own mind (as well as she could, for the
hot day made her feel very sleepy and stupid), whether the pleasure of
making a daisy-chain would be worth the trouble of getting up and
picking the daisies, when suddenly a White Rabbit with pink eyes ran
close by her.

There was nothing so very remarkable in that; nor did Alice think it so
very much out of the way to hear the Rabbit say to itself, "Oh dear! Oh
dear! I shall be late!" (when she thought it over afterwards, it
occurred to her that she ought to have wondered at this, but at the time
it all seemed quite natural); but when the Rabbit actually took a watch
out of its waistcoat-pocket, and looked at it, and then hurried on,
Alice started to her feet, for it flashed across her mind that she had
never before seen a rabbit with either a waistcoat-pocket, or a watch to
take out of it, and burning with curiosity, she ran across the field
after it, and fortunately was just in time to see it pop down a large
rabbit-hole under the hedge.


CHAPTER II. The Pool of Tears

"Curiouser and curiouser!" cried Alice (she was so much surprised, that
for the moment she quite forgot how to speak good English); "now I'm
opening out like the largest telescope that ever was! Good-bye, feet!"
(for when she looked down at her feet, they seemed to be almost out of
sight, they were getting so far off).
"""


def write_samples() -> None:
    with open(os.path.join(HERE, "euc-kr.txt"), "wb") as f:
        f.write(KOREAN.replace("\n", "\r\n").encode("cp949"))
    with open(os.path.join(HERE, "utf8.txt"), "wb") as f:
        f.write(ENGLISH.encode("utf-8"))
    print("wrote euc-kr.txt (cp949, CRLF) and utf8.txt (utf-8, LF)")


def write_big(path: str, chapters: int, mb: float) -> None:
    rng = random.Random(1)
    words = ["바람이", "불었다.", "그는", "천천히", "걸었다.", "밤은", "깊었고", "달빛이",
             "창문을", "비추었다.", "누군가", "문을", "두드렸다.", "아무도", "대답하지", "않았다."]
    target = int(mb * 1024 * 1024)
    per_chapter = max(target // chapters, 1000)
    with open(path, "w", encoding="utf-8") as f:
        f.write("큰 파일 시험용\n\n")
        for n in range(1, chapters + 1):
            f.write(f"제{n}장 {n}번째 이야기\n\n")
            written = 0
            while written < per_chapter:
                para = " ".join(rng.choice(words) for _ in range(rng.randint(20, 60)))
                f.write(para + "\n\n")
                written += len(para.encode("utf-8")) + 2
    print(f"wrote {path}: {os.path.getsize(path) / 1048576:.1f} MB, {chapters} chapters")


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--big", metavar="PATH")
    ap.add_argument("--chapters", type=int, default=300)
    ap.add_argument("--mb", type=float, default=10)
    a = ap.parse_args()
    if a.big:
        write_big(a.big, a.chapters, a.mb)
    else:
        write_samples()
