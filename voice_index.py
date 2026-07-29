"""Searchable index of every VOICED retail line - for writing new dialogue
that still speaks with the original actors.

Why this works: a dialog line's `cue` field names an XACT cue (Sounds.xsb holds
7578 of them; the audio lives in XACT\\win\\UnitTalk.xwb, lip sync in
LipSync\\data.lipsync). Put an existing cue name on a NEW dialog line and the
engine plays that original recording, with lip sync, for free - no audio
extraction, no new files, no engine changes.

The price: the subtitle must match the recording, so new dialogue has to be
ASSEMBLED from sentences the actors already spoke. This tool finds them.

Voiced material available (German retail):
    hero  (lector 1)   1820 lines   CUE_0001_*
    Kira  (lector 3)     37 lines   CUE_0003_*
    Gandohar (lector 2) 101 lines   CUE_0002_*
    ... plus ~5600 more across every other speaker.

Usage:
    python voice_index.py <suchwort> [...]     # search all voiced lines
    python voice_index.py --lector 1 <wort>    # only the hero
    python voice_index.py --short 1            # hero one-liners (reusable glue)
    python voice_index.py --dump 3             # every Kira line with its cue
"""

import re
import sys

import questforge
import tw1_lan

LECTORS = {1: 'HERO', 2: 'GANDOHAR', 3: 'KIRA', 166: 'FERID'}


def load():
    """[(lector, cue, text, dq_id)] for every voiced line, deduped by cue."""
    tr, _, rest = tw1_lan.read(open(questforge.BASE_LAN, 'rb').read())
    seen, out = set(), []
    for t in tw1_lan.parse_trees(rest):
        for e in t.entries:
            txt = tr.get(e.tid, '').strip()
            if e.cue and txt and e.cue not in seen:
                seen.add(e.cue)
                out.append((e.lector, e.cue, txt, t.id))
    return out


def who(lector):
    return LECTORS.get(lector, f'l{lector}')


def show(rows, limit=40):
    for lec, cue, txt, dq in rows[:limit]:
        print(f'  [{who(lec):8}] {cue:14} {txt}')
    if len(rows) > limit:
        print(f'  ... und {len(rows) - limit} weitere')


def main():
    args = sys.argv[1:]
    rows = load()
    if not args:
        from collections import Counter
        c = Counter(lec for lec, _, _, _ in rows)
        print(f'{len(rows)} vertonte Zeilen insgesamt. Top-Sprecher:')
        for lec, n in c.most_common(12):
            print(f'  {who(lec):8} {n:5} Zeilen')
        print('\n' + __doc__.split('Usage:')[1])
        return

    lector = None
    if args[0] == '--lector':
        lector = int(args[1]); args = args[2:]
    if args and args[0] == '--dump':
        lec = int(args[1])
        sel = [r for r in rows if r[0] == lec]
        print(f'{who(lec)}: {len(sel)} vertonte Zeilen')
        show(sel, limit=10**6)
        return
    if args and args[0] == '--short':
        lec = int(args[1])
        sel = [r for r in rows if r[0] == lec and len(r[2]) <= 45]
        print(f'{who(lec)}: {len(sel)} kurze Zeilen (<=45 Zeichen) - '
              f'ideal als Bindeglieder')
        show(sel, limit=10**6)
        return

    pat = re.compile('|'.join(re.escape(a) for a in args), re.I)
    sel = [r for r in rows
           if pat.search(r[2]) and (lector is None or r[0] == lector)]
    print(f'{len(sel)} Treffer fuer {args}'
          + (f' (nur {who(lector)})' if lector else ''))
    show(sel)


if __name__ == '__main__':
    main()
