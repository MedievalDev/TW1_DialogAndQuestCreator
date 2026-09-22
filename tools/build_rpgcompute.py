"""Build the RPGCompute template: the hero's experience curve and the values
of the enemies (4.5.0).

Needs the SDK (EarthC). Run once whenever the unit list changes; the tool
ships the result in questforge2/assets/rpgcompute and only writes numbers
into it (rpgcompute.py), the same way the quest limit is patched.

RPGCompute is the script the engine asks for everything that is computed
per unit (SDK Scripts\\RPGCompute), so values changed there count whatever
TwoWorlds.par another mod brings (a campaign ships its own par and wins
over ours; measured 2026-09-22 with Yamalin.wd). The template adds:

1. The experience curve (Unit.ech GetExperiencePointsForLevel):
   BaseExperience(n) * PERCENT / 100, PERCENT = mov edx, imm32 (CURVE).
2. A table per enemy unit (EnemyStats.ech, one ES call per unit, 16
   numbers, pushed as mov eax, imm32 / push eax): percent and amount for
   the health base, the strike pause and the four protections, the damage
   percent, percent and amount for the kill experience; ESG(active, floor)
   with two marker values. Hooks:
   - UpdateValues: initParamHP, strikeDelayTicks and initProtect of the
     unit go through the table (base * percent / 100 + amount);
   - InitMissile (melee strikes are missiles too): all damage values of
     the attacker's missile times its damage percent;
   - OnHitSuccess: when the hero's hit left the enemy dead, the kill
     experience of the table on top of what the engine gives (the unit's
     level): level * (percent - 100) / 100 + amount, not below minus the
     level when "floor" is on; the unit gets the attribute QCXP so a
     second hit on the corpse gives nothing.
Everything else must stay the game's script: the untouched SDK source is
compiled first and has to give exactly the RPGCompute.eco of Update16.wd.

Usage: py -3.12 tools/build_rpgcompute.py [SDK folder]
"""
import hashlib
import json
import os
import re
import shutil
import struct
import subprocess
import sys
import tempfile

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
from questforge2 import data, enemylevel, questlimit  # noqa: E402

SDK = sys.argv[1] if len(sys.argv) > 1 else r'D:\Games\TwoWorldsSDK'
OUT = os.path.join(ROOT, 'questforge2', 'assets', 'rpgcompute')
INNER = questlimit.SEP.join(('Scripts', 'RPGCompute', 'RPGCompute.eco'))
CURVE = 31337
ACTIVE, FLOOR = 7340033, 7340034
FIELDS = ('hp_p', 'hp_a', 'dmg_p', 'st_p', 'st_a', 'phys_p', 'phys_a',
          'cold_p', 'cold_a', 'fire_p', 'fire_a', 'elec_p', 'elec_a',
          'xp_p', 'xp_a')
NEUTRAL = {k: (100 if k.endswith('_p') else 0) for k in FIELDS}


def units():
    """Every unit of the level window once, in table order."""
    seen, out = set(), []
    for e in enemylevel.all_entries():
        for u in e[6]:
            if u not in seen:
                seen.add(u)
                out.append(u)
    return out


def include_text(names):
    n = len(names)
    L = ['// Values per enemy unit (TW1 Quest Creator 4.5.0). The tool',
         '// overwrites the numbers of the ES and ESG calls.',
         '#ifndef QC_ENEMYSTATS_ECH', '#define QC_ENEMYSTATS_ECH', '',
         'int bEsActive;', 'int bEsFloor;']
    L += [f'int anEs_{k}[{n}];' for k in FIELDS]
    L += ['', 'function void ESG(int bActive, int bFloor)', '{',
          '    bEsActive = bActive;', '    bEsFloor = bFloor;', '}', '']
    args = ', '.join(f'int n_{k}' for k in FIELDS)
    L += [f'function void ES(int nUnit, {args})', '{']
    L += [f'    anEs_{k}[nUnit] = n_{k};' for k in FIELDS]
    L += ['}', '', 'function void InitializeEnemyStats()', '{',
          f'    ESG({ACTIVE}, {FLOOR});']
    neutral = ', '.join(str(NEUTRAL[k]) for k in FIELDS)
    L += [f'    ES({i}, {neutral});' for i in range(n)]
    L += ['}', '',
          'function int EsIndex(unit pUnit)', '{', '    string str;',
          '    if ((bEsActive == 0) || (pUnit == null)) return -1;',
          '    str = pUnit.GetObjectIDName();']
    L += [f'    if (str.EqualNoCase("{u}")) return {i};'
          for i, u in enumerate(names)]
    L += ['    return -1;', '}', '',
          'function int EsValue(int nBase, int nPercent, int nAmount)', '{',
          '    return nBase * nPercent / 100 + nAmount;', '}', '',
          'function int EsHP(int nEs, int nBase)', '{',
          '    if (nEs < 0) return nBase;',
          '    return MAX(EsValue(nBase, anEs_hp_p[nEs], anEs_hp_a[nEs]), 1);',
          '}', '',
          'function int EsStrike(int nEs, int nBase)', '{',
          '    if (nEs < 0) return nBase;',
          '    return MAX(EsValue(nBase, anEs_st_p[nEs], anEs_st_a[nEs]), 1);',
          '}', '',
          'function int EsProtect(int nEs, int nIndex, int nBase)', '{',
          '    if (nEs < 0) return nBase;',
          '    if (nIndex == 0) return EsValue(nBase, anEs_phys_p[nEs], anEs_phys_a[nEs]);',
          '    if (nIndex == 1) return EsValue(nBase, anEs_cold_p[nEs], anEs_cold_a[nEs]);',
          '    if (nIndex == 2) return EsValue(nBase, anEs_fire_p[nEs], anEs_fire_a[nEs]);',
          '    if (nIndex == 3) return EsValue(nBase, anEs_elec_p[nEs], anEs_elec_a[nEs]);',
          '    return nBase;', '}', '',
          'function void EsDamage(unit pUnit, MissileValues mVal)', '{',
          '    int nEs;', '    int nIndex;',
          '    nEs = EsIndex(pUnit);',
          '    if (nEs < 0) return;',
          '    if (anEs_dmg_p[nEs] == 100) return;',
          '    for (nIndex = 0; nIndex <= eDamagePoison; nIndex++)', '    {',
          '        mVal.SetDamage(nIndex, mVal.GetDamage(nIndex) * anEs_dmg_p[nEs] / 100);',
          '    }', '}', '',
          'function void EsKillExp(unit pUnit, unit pEnemy)', '{',
          '    int nEs;', '    int nLevel;', '    int nBonus;', '    int nExp;',
          '    int nDone;',
          '    if ((pUnit == null) || (pEnemy == null)) return;',
          '    if (!pUnit.IsHeroUnit() || !pEnemy.IsUnit()) return;',
          '    if (pEnemy.IsLive() && (pEnemy.GetUnitValues().GetCurrHP() > 0)) return;',
          '    nEs = EsIndex(pEnemy);',
          '    if (nEs < 0) return;',
          '    if ((anEs_xp_p[nEs] == 100) && (anEs_xp_a[nEs] == 0)) return;',
          '    nDone = 0;',
          '    pEnemy.GetAttribute("QCXP", nDone);',
          '    if (nDone != 0) return;',
          '    pEnemy.SetAttribute("QCXP", 1);',
          '    nLevel = pEnemy.GetUnitValues().GetLevel();',
          '    nBonus = nLevel * (anEs_xp_p[nEs] - 100) / 100 + anEs_xp_a[nEs];',
          '    if ((bEsFloor != 0) && (nBonus < -nLevel)) nBonus = -nLevel;',
          '    if (nBonus == 0) return;',
          '    nExp = pUnit.GetUnitValues().GetExperiencePoints() + nBonus;',
          '    if (nExp < 0) nExp = 0;',
          '    pUnit.GetUnitValues().SetExperiencePoints(nExp);',
          '}', '', '#endif']
    return '\n'.join(L) + '\n'


# -- source changes (every replacement asserted) -------------------------------

def rep(src, a, b, n=1):
    assert src.count(a) == n, (a[:60], src.count(a))
    return src.replace(a, b)


CURVE_OLD = """    return CalcExperiencePointsForLevel(nLevel, GetExperiencePointsForLevel(nLevel - 1));
}"""


def patch_unit(src):
    # 1. the curve
    src = rep(src, 'function int GetExperiencePointsForLevel(int nLevel)',
              'function int GetBaseExperiencePointsForLevel(int nLevel)')
    src = rep(src, CURVE_OLD, """    return CalcExperiencePointsForLevel(nLevel, GetBaseExperiencePointsForLevel(nLevel - 1));
}

// Quest Creator 4.5.0: the curve times a percent the tool writes in
function int GetExperiencePointsForLevel(int nLevel)
{
    return (GetBaseExperiencePointsForLevel(nLevel) * %d) / 100;
}""" % CURVE)
    # 2. the table
    src = rep(src, '#include "..\\common\\achievements.ech"',
              '#include "..\\common\\achievements.ech"\n'
              '#include "EnemyStats.ech"')
    src = rep(src, """    int bMaxHP, bMaxMana;
    int nTmp;
""", """    int bMaxHP, bMaxMana;
    int nTmp;
    int nEs;
""")
    src = rep(src, """    nUnitLevel = unVal.GetLevel();

    if (unVal.GetCurrHP() == unVal.GetParam(eParamHP))""",
              """    nUnitLevel = unVal.GetLevel();
    nEs = EsIndex(pUnit);

    if (unVal.GetCurrHP() == unVal.GetParam(eParamHP))""")
    src = rep(src, 'arrParams[eParamHP]      = unPar.GetInitParam(eParamHP)*(10+',
              'arrParams[eParamHP]      = EsHP(nEs, unPar.GetInitParam(eParamHP))*(10+')
    src = rep(src, 'unVal.SetStrikeDelayTicks(unPar.GetStrikeDelayTicks());',
              'unVal.SetStrikeDelayTicks(EsStrike(nEs, unPar.GetStrikeDelayTicks()));')
    src = rep(src, 'nSum = unPar.GetInitProtect(nIndex) + unVal.GetBasicProtect(nIndex);',
              'nSum = EsProtect(nEs, nIndex, unPar.GetInitProtect(nIndex)) + unVal.GetBasicProtect(nIndex);')
    # InitMissile (the full one): damage times the attacker's percent
    head = ('function void InitMissile(unit pUnit, int nCurrentFightAction, '
            'MissileValues mVal, MissileParams mPar, EquipmentValues wVal, '
            'WeaponParams wPar, unit pEnemy)\n{')
    i = src.index(head)
    j = src.index('\n}//', i)
    src = src[:j] + '\n    EsDamage(pUnit, mVal);' + src[j:]
    # OnHitSuccess: the kill experience first (the function may return)
    src = rep(src, """function void OnHitSuccess(unit pUnit, unit pEnemy, int nFightAction, int nHPDamage, int bByPoison, int bFirstMissileHit)
{
""", """function void OnHitSuccess(unit pUnit, unit pEnemy, int nFightAction, int nHPDamage, int bByPoison, int bFirstMissileHit)
{
    EsKillExp(pUnit, pEnemy);
""")
    return src


def patch_main(src):
    """RPGCompute.ec: the table filled when the script starts."""
    m = re.search(r'command Initialize\(\)\s*\{\n', src)
    assert m, 'command Initialize'
    return src[:m.end()] + '    InitializeEnemyStats();\n' + src[m.end():]


# -- compiling -------------------------------------------------------------------

def compile_script(folder, name):
    eco = os.path.join(folder, name + 'o')
    if os.path.exists(eco):
        os.remove(eco)
    bat = os.path.join(SDK, 'Tools', 'EarthC.bat')
    r = subprocess.run(['cmd', '/c', bat, name], cwd=folder,
                       capture_output=True, text=True,
                       stdin=subprocess.DEVNULL, timeout=600)
    if not os.path.isfile(eco):
        print(r.stdout[-3000:], r.stderr[-3000:])
        raise SystemExit(f'EarthC failed on {name}')
    with open(eco, 'rb') as f:
        return questlimit.eco_body(f.read())


def game_body():
    g = data.find_game_dir()
    p = os.path.join(g, 'WDFiles', 'Update16.wd')
    e = next(x for x in questlimit.wd_entries(p) if x['path'] == INNER)
    return questlimit.eco_body(questlimit.wd_read_file(p, e)), e


def rewrite(path, fn):
    with open(path, 'rb') as f:
        raw = f.read()
    crlf = b'\r\n' in raw
    src = raw.decode('latin-1').replace('\r\n', '\n')
    with open(path, 'w', encoding='latin-1',
              newline='\r\n' if crlf else '\n') as f:
        f.write(fn(src))


def imm_sites(body, value):
    return [i for i in range(len(body) - 3)
            if body[i:i + 4] == struct.pack('<I', value & 0xFFFFFFFF)]


def table_sites(body, n_units):
    """Offsets of the 16 immediates of every ES call, unit order. The
    arguments go on the stack right to left: the last field first, the
    unit number last."""
    pat = re.compile(rb'(?:\xb8.{4}\x50){16}\xe8', re.S)
    calls = {}
    for m in pat.finditer(body):
        offs = [m.start() + k * 6 + 1 for k in range(16)]
        vals = [struct.unpack_from('<i', body, o)[0] for o in offs]
        unit = vals[-1]
        fields = list(reversed(vals[:-1]))
        if 0 <= unit < n_units and fields == [NEUTRAL[k] for k in FIELDS] \
                and unit not in calls:
            calls[unit] = list(reversed(offs[:-1]))
    if sorted(calls) != list(range(n_units)):
        raise SystemExit(f'ES calls found for {len(calls)} of {n_units} units')
    return [calls[i] for i in range(n_units)]


def main():
    retail, entry = game_body()
    names = units()
    work = tempfile.mkdtemp(prefix='rpgcompute_')
    try:
        shutil.copytree(os.path.join(SDK, 'Scripts'),
                        os.path.join(work, 'Scripts'))
        folder = os.path.join(work, 'Scripts', 'RPGCompute')
        plain = compile_script(folder, 'RPGCompute.ec')
        print('SDK source:', len(plain), 'bytes, game:', len(retail))
        if plain != retail:
            raise SystemExit('the SDK source does not compile to the '
                             'RPGCompute.eco of Update16.wd')
        with open(os.path.join(folder, 'EnemyStats.ech'), 'w',
                  encoding='latin-1', newline='\r\n') as f:
            f.write(include_text(names))
        rewrite(os.path.join(folder, 'Unit.ech'), patch_unit)
        rewrite(os.path.join(folder, 'RPGCompute.ec'), patch_main)
        body = compile_script(folder, 'RPGCompute.ec')
        curve = imm_sites(body, CURVE)
        active, floor = imm_sites(body, ACTIVE), imm_sites(body, FLOOR)
        print('template:', len(body), 'bytes; curve', curve, 'active', active,
              'floor', floor)
        for what, s in (('curve', curve), ('active', active),
                        ('floor', floor)):
            if len(s) != 1:
                raise SystemExit(f'{what} marker must appear exactly once')
        table = table_sites(body, len(names))
        os.makedirs(OUT, exist_ok=True)
        with open(os.path.join(OUT, 'RPGCompute.eco.body'), 'wb') as f:
            f.write(body)
        meta = {'format': 1, 'curve_marker': CURVE, 'curve_site': curve[0],
                'active_site': active[0], 'floor_site': floor[0],
                'fields': list(FIELDS), 'units': names, 'table': table,
                'game_sha256': hashlib.sha256(retail).hexdigest(),
                'template_sha256': hashlib.sha256(body).hexdigest(),
                'flags': entry['flags'], 'class_id': entry['id']}
        with open(os.path.join(OUT, 'rpgcompute.json'), 'w', encoding='ascii',
                  newline='\n') as f:
            json.dump(meta, f)
        print('->', OUT, len(names), 'units')
    finally:
        shutil.rmtree(work, ignore_errors=True)


if __name__ == '__main__':
    main()
