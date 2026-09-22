"""Sounds.xsb zerlegen und wieder zusammensetzen.

Erste Probe ist der Round-Trip: die Datei aus den geparsten Strukturen
byteidentisch neu erzeugen. Gelingt das, ist das Format verstanden; gelingt es
nicht, hat man es frueh gemerkt statt an einer toten Tonspur.

Aufbau (an der echten Datei nachgemessen):

      0  Kopf                 148 B
    148  Wave-Bank-Namen      256 B = 4 x 64
    404  Sounds           194.799 B = 8421 Saetze variabler Laenge
195.203  einfache Cues     42.055 B = 8411 x 5
237.258  komplexe Cues        240 B = 16 x 15
237.498  Variationen          554 B
238.052  Eimerkoepfe       16.854 B = 8427 x u16, 0xFFFF = leer
254.906  Cue-Namenstabelle 50.562 B = 8427 x 6 { u32 Namensoffset, u16 naechster }
305.468  Cue-Namen        122.331 B bis exakt Dateiende

Die beiden letzten Tabellen bilden eine Hashtabelle mit Verkettung. Der
Eimerkopf zeigt auf den ersten Cue im Eimer, jeder Satz auf den naechsten.

Wichtig fuers Erweitern: die Bloecke liegen in dieser Reihenfolge in der Datei,
und der Kopf haelt zu jedem einen Offset. Waechst ein Block, verschieben sich
alle dahinter - und die Offsets im Kopf muessen mitwandern. Die Verweise der
Cue-Saetze in den Sounds-Block bleiben gueltig, solange neue Sounds ANGEHAENGT
werden statt eingeschoben.
"""
import struct

# Feldpositionen im Kopf. Alles andere bleibt beim Neubau unveraendert -
# was nicht verstanden ist, wird nicht angefasst.
K_SIMPLE_N = 19        # u16
K_COMPLEX_N = 21       # u16
K_TOTAL_N = 25         # u16
K_BANKS_N = 27         # u8
K_SOUNDS_N = 28        # u16
K_NAMES_LEN = 32       # u32
K_SIMPLE_OFF = 36      # u32
K_COMPLEX_OFF = 40     # u32
K_NAMES_OFF = 44       # u32
K_VARI_OFF = 52        # u32
K_BANKS_OFF = 60       # u32
K_BUCKETS_OFF = 64     # u32
K_TABLE_OFF = 68       # u32
K_SOUNDS_OFF = 72      # u32
KOPF_LEN = 148

CUE_LEN = 5            # u8 Flags, u32 Offset in den Sounds-Block
TABLE_LEN = 6          # u32 Namensoffset, u16 naechster im Eimer
COMPLEX_LEN = 15
BANKNAME_LEN = 64
LEER = 0xFFFF


K_PRUEFSUMME = 8       # u16
K_FORMAT = 6           # u16, muss 42 bleiben
PRUEFBEREICH = 18      # die Pruefsumme deckt Byte 18 bis Dateiende


def cue_hash(name):
    """16-Bit-Akkumulator, laeuft ueber. Siehe tw1_xact.cue_hash."""
    h = 0
    for c in name.encode('latin-1') if isinstance(name, str) else name:
        h = (((h * 7) >> 1) + c) & 0xFFFF
    return h


def fcs16(b):
    """CRC-16/X-25: Polynom 0x8408 reflektiert, Start 0xFFFF, Ergebnis invertiert.

    Steht als u16 bei Offset 8 und deckt Byte 18 bis Dateiende ab. Das
    Ladeprogramm prueft sie wirklich und bricht sonst ab, bevor es ueberhaupt
    zu parsen anfaengt. Nachgerechnet an Sounds.xsb (0x659C) und an
    sounds.xgs (0x22E3) - zwei unabhaengige Dateien, beide stimmen.
    """
    h = 0xFFFF
    for c in b:
        h ^= c
        for _ in range(8):
            h = (h >> 1) ^ 0x8408 if h & 1 else h >> 1
    return h ^ 0xFFFF


# Ein Sprachsatz ist immer dieselben 19 Byte, nur die Spur wechselt - so
# gebaut in 7578 von 7586 Faellen. Die acht Ausreisser sind die Todesschreie
# NPC_DIE_7..14, die haengen noch einen DSP-Block an.
#
#   02          Flags: Bit0=0 einfacher Sound, Bit1=1 es folgt ein RPC-Block
#   05 00       u16 Kategorie 5 = UnitTalk
#   7f          u8  Lautstaerke 127
#   00 00       i16 Tonhoehe 0
#   00          u8  Rang 0
#   13 00       u16 Satzlaenge 19 - daran hangelt sich der Parser weiter
#   LL HH       u16 Spur = Eintrag in UnitTalk.xwb
#   03          u8  Wave-Bank 3 (FX, Music, FXf, UnitTalk)
#   07 00       u16 Laenge des RPC-Blocks, sich selbst eingerechnet
#   01          u8  ein RPC-Preset
#   0f 02 00 00 u32 527 = Offset des Presets in sounds.xgs
SPRACHSATZ_LEN = 19


def sprachsatz(spur, bank=3, kategorie=5, lautstaerke=127):
    return (struct.pack('<BHBhBH', 0x02, kategorie, lautstaerke, 0, 0,
                        SPRACHSATZ_LEN)
            + struct.pack('<HB', spur, bank)
            + bytes.fromhex('07 00 01 0f 02 00 00'.replace(' ', '')))


class Xsb:
    """Zerlegte Sound-Bank. Blockgrenzen bleiben erhalten, solange nichts
    hinzukommt - deshalb ist der Round-Trip byteidentisch moeglich."""

    def __init__(self, data):
        self.roh = bytes(data)
        d = self.roh
        if d[:4] != b'SDBK':
            raise ValueError(f'keine XACT-Sound-Bank: {d[:4]!r}')
        self.kopf = bytearray(d[:KOPF_LEN])

        self.n_simple = struct.unpack_from('<H', d, K_SIMPLE_N)[0]
        self.n_complex = struct.unpack_from('<H', d, K_COMPLEX_N)[0]
        self.n_total = struct.unpack_from('<H', d, K_TOTAL_N)[0]
        self.n_banks = d[K_BANKS_N]
        self.n_sounds = struct.unpack_from('<H', d, K_SOUNDS_N)[0]
        self.names_len = struct.unpack_from('<I', d, K_NAMES_LEN)[0]

        self.off_simple = struct.unpack_from('<I', d, K_SIMPLE_OFF)[0]
        self.off_complex = struct.unpack_from('<I', d, K_COMPLEX_OFF)[0]
        self.off_names = struct.unpack_from('<I', d, K_NAMES_OFF)[0]
        self.off_vari = struct.unpack_from('<I', d, K_VARI_OFF)[0]
        self.off_banks = struct.unpack_from('<I', d, K_BANKS_OFF)[0]
        self.off_buckets = struct.unpack_from('<I', d, K_BUCKETS_OFF)[0]
        self.off_table = struct.unpack_from('<I', d, K_TABLE_OFF)[0]
        self.off_sounds = struct.unpack_from('<I', d, K_SOUNDS_OFF)[0]

        # Bloecke als Rohbytes. Was nicht angefasst wird, bleibt so wie es ist.
        self.banks_roh = d[self.off_banks:self.off_sounds]
        self.sounds_roh = bytearray(d[self.off_sounds:self.off_simple])
        self.simple_roh = bytearray(
            d[self.off_simple:self.off_simple + self.n_simple * CUE_LEN])
        self.complex_roh = d[self.off_complex:self.off_vari]
        self.vari_roh = d[self.off_vari:self.off_buckets]

        # Namen in Cue-Reihenfolge, plus die Verkettung.
        self.namen = []
        o = self.off_names
        for _ in range(self.n_total):
            e = d.index(b'\0', o)
            self.namen.append(d[o:e].decode('latin-1'))
            o = e + 1
        self._idx = {n: i for i, n in enumerate(self.namen)}

        self.baenke = [
            self.banks_roh[i * BANKNAME_LEN:(i + 1) * BANKNAME_LEN]
            .split(b'\0')[0].decode('latin-1') for i in range(self.n_banks)]

    # -- lesen -----------------------------------------------------------
    def cue_sound_offset(self, i):
        """Offset des Sound-Satzes eines einfachen Cues."""
        return struct.unpack_from('<I', self.simple_roh, i * CUE_LEN + 1)[0]

    def cue_flags(self, i):
        return self.simple_roh[i * CUE_LEN]

    def sound_wave(self, off):
        """(Bankname, Wave-Index) eines einfachen Sound-Satzes, sonst None."""
        rel = off - self.off_sounds
        flags = self.sounds_roh[rel]
        if flags & 1:
            return None
        track, bank = struct.unpack_from('<HB', self.sounds_roh, rel + 9)
        return self.baenke[bank], track

    def wave_of(self, name):
        i = self._idx.get(name)
        if i is None or i >= self.n_simple:
            return None
        return self.sound_wave(self.cue_sound_offset(i))

    def eimer(self):
        """{Cue-Index: Eimer}, gewonnen durch Ablaufen aller Ketten."""
        d = self.roh
        aus = {}
        for b in range(self.n_total):
            i = struct.unpack_from('<H', d, self.off_buckets + b * 2)[0]
            while i != LEER:
                aus[i] = b
                i = struct.unpack_from('<H', d,
                                       self.off_table + i * TABLE_LEN + 4)[0]
        return aus

    def spur_setzen(self, name, spur, bank=3):
        """Einen VORHANDENEN Cue auf eine andere Aufnahme richten.

        Aendert nur die zwei Byte Spurnummer im Sound-Satz. Der Cue-Name, die
        Hashtabellen und alle Offsets bleiben unangetastet - fuer die Engine
        ist es derselbe Cue wie vorher, er zeigt nur woandershin.

        Damit laesst sich pruefen, ob es an der NEUHEIT eines Cues liegt: die
        Aufnahme ist unsere, der Name einer, den das Spiel schon kennt.
        """
        i = self._idx.get(name)
        if i is None or i >= self.n_simple:
            raise ValueError(f'kein einfacher Cue: {name}')
        rel = self.cue_sound_offset(i) - self.off_sounds
        if self.sounds_roh[rel] & 1:
            raise ValueError(f'{name} haengt an einem komplexen Sound')
        struct.pack_into('<HB', self.sounds_roh, rel + 9, spur, bank)

    # -- erweitern -------------------------------------------------------
    def cue_anlegen(self, name, spur, bank=3, lautstaerke=127):
        """Neuen Sprach-Cue anhaengen: Name, Sound-Satz, Cue-Satz.

        Der Sound-Satz wird ANS ENDE des Sounds-Blocks gehaengt, damit die
        u32-Verweise aller bestehenden Cue-Saetze gueltig bleiben - der Block
        waechst nur nach hinten, sein Anfang bleibt bei 404.

        Der Cue-Satz kommt ans Ende der einfachen Cues. Damit verschiebt sich
        alles dahinter; bauen() rechnet die Kopf-Offsets neu und zieht die
        absoluten Verweise der komplexen Cues in die Variationstabelle mit.
        """
        if name in self._idx:
            raise ValueError(f'Cue heisst schon so: {name}')
        if self.n_total + 1 > 0xFFFE:
            raise ValueError('mehr als 65.534 Cues gehen nicht - '
                             'der Kettenzeiger ist u16 mit 0xFFFF als Ende')

        sound_off = self.off_sounds + len(self.sounds_roh)
        self.sounds_roh += sprachsatz(spur, bank,
                                      lautstaerke=lautstaerke)
        self.n_sounds += 1

        # Flags 4 wie bei allen 8411 vorhandenen einfachen Cues.
        self.simple_roh += struct.pack('<BI', 4, sound_off)
        self.n_simple += 1

        # Die Namen stehen in Cue-Reihenfolge; einfache Cues kommen vor den
        # komplexen, der neue Name also VOR die 16 komplexen.
        self.namen.insert(self.n_simple - 1, name)
        self.n_total += 1
        self._idx = {n: i for i, n in enumerate(self.namen)}
        return self.n_simple - 1

    # -- schreiben -------------------------------------------------------
    def bauen(self):
        """Die Datei aus den Bestandteilen neu zusammensetzen.

        Die Hashtabellen werden aus den Namen NEU berechnet, nicht kopiert -
        genau das muss beim Erweitern ja auch geschehen. Kommt dabei die
        Originaldatei heraus, stimmt die Hashfunktion und die Kettenbildung.
        """
        namen_bytes = bytearray()
        namens_offset = []
        for n in self.namen:
            namens_offset.append(len(namen_bytes))
            namen_bytes += n.encode('latin-1') + b'\0'

        off_banks = KOPF_LEN
        off_sounds = off_banks + len(self.banks_roh)
        off_simple = off_sounds + len(self.sounds_roh)
        off_complex = off_simple + len(self.simple_roh)
        off_vari = off_complex + len(self.complex_roh)
        off_buckets = off_vari + len(self.vari_roh)
        off_table = off_buckets + self.n_total * 2
        off_names = off_table + self.n_total * TABLE_LEN

        # Eimer neu bilden. Die Reihenfolge innerhalb eines Eimers ist die
        # Originalreihenfolge: der zuletzt eingehaengte Cue steht vorn, also
        # rueckwaerts einhaengen, damit die Kette wie im Original laeuft.
        koepfe = [LEER] * self.n_total
        naechster = [LEER] * self.n_total
        for i in range(self.n_total - 1, -1, -1):
            b = cue_hash(self.namen[i]) % self.n_total
            naechster[i] = koepfe[b]
            koepfe[b] = i

        kopf = bytearray(self.kopf)
        struct.pack_into('<I', kopf, K_NAMES_LEN, len(namen_bytes))
        struct.pack_into('<I', kopf, K_SIMPLE_OFF, off_simple)
        struct.pack_into('<I', kopf, K_COMPLEX_OFF, off_complex)
        struct.pack_into('<I', kopf, K_NAMES_OFF, off_names)
        struct.pack_into('<I', kopf, K_VARI_OFF, off_vari)
        struct.pack_into('<I', kopf, K_BANKS_OFF, off_banks)
        struct.pack_into('<I', kopf, K_BUCKETS_OFF, off_buckets)
        struct.pack_into('<I', kopf, K_TABLE_OFF, off_table)
        struct.pack_into('<I', kopf, K_SOUNDS_OFF, off_sounds)
        struct.pack_into('<H', kopf, K_SIMPLE_N, self.n_simple)
        struct.pack_into('<H', kopf, K_COMPLEX_N, self.n_complex)
        struct.pack_into('<H', kopf, K_TOTAL_N, self.n_total)
        struct.pack_into('<H', kopf, K_SOUNDS_N, self.n_sounds)

        # Die 16 komplexen Cues halten absolute Offsets in die
        # Variationstabelle. Waechst der Block davor, wandern die mit.
        verschub = off_vari - self.off_vari
        komplex = bytearray(self.complex_roh)
        if verschub:
            for i in range(self.n_complex):
                p = i * COMPLEX_LEN + 1
                z = struct.unpack_from('<I', komplex, p)[0]
                if z != 0xFFFFFFFF:
                    struct.pack_into('<I', komplex, p, z + verschub)
            # Die Variationseintraege zeigen auf Sound-Saetze. Der
            # Sounds-Block faengt unveraendert bei 404 an und waechst nur
            # nach hinten, diese Verweise bleiben also gueltig.

        aus = bytearray(kopf)
        aus += self.banks_roh
        aus += self.sounds_roh
        aus += self.simple_roh
        aus += komplex
        aus += self.vari_roh
        for b in koepfe:
            aus += struct.pack('<H', b)
        for i in range(self.n_total):
            aus += struct.pack('<IH', off_names + namens_offset[i],
                               naechster[i])
        aus += namen_bytes

        # Zum Schluss die Pruefsumme, wenn alle Offsets stehen.
        struct.pack_into('<H', aus, K_PRUEFSUMME, fcs16(aus[PRUEFBEREICH:]))
        return bytes(aus)
