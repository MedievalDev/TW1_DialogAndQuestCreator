"""sounds.xap.info lesen, schreiben und erweitern.

Warum diese Datei ueberhaupt zaehlt: Two Worlds holt sich Ton und Haltezeit
einer Dialogzeile aus ZWEI verschiedenen Quellen.

    Ton   ueber den Sound-Satz in Sounds.xsb
    Dauer ueber die Stellung des WAV-Eintrags in sounds.xap.info

Nachgewiesen im Spiel: biegt man einen vorhandenen Cue im Sound-Satz auf eine
neue Aufnahme um, kommt der neue Ton - aber die Haltezeit gehoert weiter zur
alten Aufnahme. Und die Positionsprobe bestaetigt es rechnerisch: bei allen
7578 UnitTalk-Eintraegen ist die Position des WAV-Eintrags in dieser Datei
genau die Wave-Nummer in der Bank, ohne eine einzige Abweichung.

Ein neuer Cue, der hier fehlt, bekommt deshalb eine Vorgabedauer von rund
einer Sekunde - egal wie lang die Aufnahme wirklich ist.

Aufbau: ein getaggter Baum aus zwei Bausteinen.

    01 <u32 Laenge> <u8 Typ> <u32 Namenslaenge> <Name> <Wert>
       Eigenschaft. Die Laenge zaehlt sich selbst mit, die Wertlaenge ergibt
       sich als Laenge - 9 - Namenslaenge.
       Typ 0x16 = Zeichenkette, 0x12 = u32

    02 <u32 Laenge> <u32 Kennung>
       Knoten. Danach folgen seine Eigenschaften und Unterknoten.

Ein Sprach-Cue besteht aus zwei Knoten:

    SND-Knoten   NameSND_0001_0001, CategoryUnitTalk, ChildCount 1
    WAV-Knoten   NameWAV_0001_0001, WaveBankNameUnitTalk
"""
import struct

EIG = 0x01           # Eigenschaft
KNOTEN = 0x02        # Knoten
T_STR = 0x16
T_U32 = 0x12


class Eigenschaft:
    __slots__ = ('typ', 'name', 'wert')

    def __init__(self, typ, name, wert):
        self.typ, self.name, self.wert = typ, name, wert

    def bauen(self):
        w = self.wert if isinstance(self.wert, bytes) else \
            struct.pack('<I', self.wert)
        n = self.name
        return (bytes([EIG]) + struct.pack('<I', 9 + len(n) + len(w))
                + bytes([self.typ]) + struct.pack('<I', len(n)) + n + w)

    def __repr__(self):
        w = self.wert if isinstance(self.wert, bytes) else str(self.wert)
        return f'{self.name.decode()}={w!r}'


class Knoten:
    __slots__ = ('kennung', 'inhalt')

    def __init__(self, kennung, inhalt=None):
        self.kennung = kennung
        self.inhalt = list(inhalt or [])

    def bauen(self):
        koerper = b''.join(k.bauen() for k in self.inhalt)
        return (bytes([KNOTEN]) + struct.pack('<II', 8 + len(koerper),
                                              self.kennung) + koerper)

    def eigenschaft(self, name):
        for k in self.inhalt:
            if isinstance(k, Eigenschaft) and k.name == name:
                return k
        return None

    def __repr__(self):
        return f'Knoten({self.kennung}, {len(self.inhalt)} Kinder)'


def _lesen(b, o, ende):
    """Eine Folge von Eigenschaften und Knoten bis `ende` einlesen."""
    aus = []
    while o < ende:
        marke = b[o]
        if marke == EIG:
            ln = struct.unpack_from('<I', b, o + 1)[0]
            typ = b[o + 5]
            nl = struct.unpack_from('<I', b, o + 6)[0]
            name = b[o + 10:o + 10 + nl]
            roh = b[o + 10 + nl:o + 1 + ln]
            wert = roh if typ != T_U32 else struct.unpack('<I', roh)[0]
            aus.append(Eigenschaft(typ, name, wert))
            o += 1 + ln
        elif marke == KNOTEN:
            ln, kennung = struct.unpack_from('<II', b, o + 1)
            k = Knoten(kennung)
            k.inhalt = _lesen(b, o + 9, o + 1 + ln)
            aus.append(k)
            o += 1 + ln
        else:
            raise ValueError(f'unbekannte Marke {marke:#04x} bei {o}')
    return aus


class Xap:
    def __init__(self, data):
        self.roh = bytes(data)
        # Vor dem ersten Knoten steht ein Kopf, dessen Aufbau nicht gebraucht
        # wird - er bleibt unangetastet.
        o = self.roh.index(bytes([KNOTEN]))
        self.kopf = self.roh[:o]
        self.inhalt = _lesen(self.roh, o, len(self.roh))

    def bauen(self):
        return self.kopf + b''.join(k.bauen() for k in self.inhalt)

    def durchlaufen(self, knoten=None):
        """Alle Knoten der Reihe nach, in Dateireihenfolge."""
        for k in (self.inhalt if knoten is None else knoten.inhalt):
            if isinstance(k, Knoten):
                yield k
                yield from self.durchlaufen(k)

    def name_von(self, k):
        e = k.eigenschaft(b'Name')
        return e.wert.decode('latin-1') if e else None

    # -- die beiden Stellen, an denen etwas dazukommen muss ---------------
    def _gruppen(self):
        wurzel = next(k for k in self.inhalt if isinstance(k, Knoten))
        return [k for k in wurzel.inhalt if isinstance(k, Knoten)]

    def wave_liste(self, bank='UnitTalk'):
        """Der Knoten mit den Wave-Eintraegen einer Bank.

        Hier steht die Dauer: PRL ist die Quelllaenge in Byte, SRATE die
        Abtastrate, und PRL/2/SRATE ergibt bei allen 8712 Eintraegen exakt
        die Dauer aus der Wave-Bank - ohne eine einzige Abweichung. Genau
        daraus nimmt die Engine die Haltezeit einer Dialogzeile.

        Die Kennung eines Wave-Knotens IST seine Nummer in der Bank.
        """
        for b in [k for k in self._gruppen()[2].inhalt
                  if isinstance(k, Knoten)]:
            if self.name_von(b) == bank:
                return b
        raise KeyError(bank)

    def cue_liste(self):
        """Der Knoten, unter dem die SND-Eintraege haengen."""
        def suche(k):
            for c in k.inhalt:
                if isinstance(c, Knoten):
                    if (self.name_von(c) or '').startswith('SND_'):
                        return k
                    t = suche(c)
                    if t is not None:
                        return t
            return None
        t = suche(self._gruppen()[1])
        if t is None:
            raise KeyError('keine SND-Eintraege gefunden')
        return t

    @staticmethod
    def _kinder(k):
        return [c for c in k.inhalt if isinstance(c, Knoten)]

    @staticmethod
    def _zaehler_setzen(k, n):
        e = k.eigenschaft(b'ChildCount')
        if e is not None:
            e.wert = n

    def wave_anlegen(self, nummer, name, prl, srate=44100, pfad=None):
        """Neuen Wave-Eintrag anhaengen. nummer muss die Bank-Nummer sein."""
        w = self.wave_liste()
        if len(self._kinder(w)) != nummer:
            raise ValueError(f'Wave {nummer} passt nicht ans Ende der Liste '
                             f'({len(self._kinder(w))} Eintraege)')
        pfad = pfad or f'Source\\UnitTalk\\mod\\{name}.wav'
        k = Knoten(nummer, [
            Eigenschaft(T_STR, b'Name', name.encode('latin-1')),
            Eigenschaft(T_STR, b'Filename', pfad.encode('latin-1')),
            Eigenschaft(T_U32, b'BPS', 1),
            Eigenschaft(T_U32, b'Channels', 1),
            Eigenschaft(T_U32, b'PRO', 4096),
            Eigenschaft(T_U32, b'PRL', prl),
            Eigenschaft(T_U32, b'SRATE', srate),
        ])
        w.inhalt.append(k)
        self._zaehler_setzen(w, len(self._kinder(w)))
        return k

    # -- sounds.xap.cued: hier steht die Haltezeit ------------------------
    #
    # DAS ist die Datei, aus der Two Worlds die Laenge einer Dialogzeile
    # nimmt - nicht die .info, die im Programm gar nicht vorkommt. Belegt:
    # in TwoWorlds.exe steht die Zeichenkette "Sounds.xap.cued".
    #
    # Aufbau: der Wurzelknoten traegt ChildCount, NumFrames und FrameData.
    # FrameData ist ein Klumpen aus Eintraegen
    #
    #     u8 Namenslaenge | Name | float32 Dauer in Sekunden
    #
    # 8427 Eintraege, genau der ChildCount, der Klumpen geht restlos auf.
    # Gegen die echten Wave-Dauern gehalten: groesste Abweichung 0,7 ms.
    # NumFrames ist nicht die Zahl der Eintraege, sondern die Laenge des
    # Klumpens in Byte.
    #
    # Der erste Eintrag heisst XXXDEFAULT und steht auf 1.0 - das ist der
    # Rueckfallwert. Wer einen Cue anlegt, ohne ihn hier einzutragen, hoert
    # seine Aufnahme und der Dialog schaltet nach einer Sekunde weiter.

    def _frames(self):
        wurzel = next(k for k in self.inhalt if isinstance(k, Knoten))
        return wurzel, wurzel.eigenschaft(b'FrameData')

    def dauern(self):
        """{Cue-Name: Sekunden} aus FrameData."""
        _w, e = self._frames()
        blob, o, aus = e.wert, 0, {}
        while o < len(blob):
            n = blob[o]
            o += 1
            name = blob[o:o + n].decode('latin-1')
            o += n
            aus[name] = struct.unpack_from('<f', blob, o)[0]
            o += 4
        return aus

    def dauer_anlegen(self, name, sekunden):
        """Einen Cue mit seiner Laenge eintragen."""
        wurzel, e = self._frames()
        roh = name.encode('latin-1')
        if len(roh) > 255:
            raise ValueError('Cue-Name zu lang fuer das Laengenbyte')
        e.wert = e.wert + bytes([len(roh)]) + roh + struct.pack('<f',
                                                               sekunden)
        for feld, wert in ((b'ChildCount',
                            wurzel.eigenschaft(b'ChildCount').wert + 1),
                           (b'NumFrames', len(e.wert))):
            wurzel.eigenschaft(feld).wert = wert

    def snd_anlegen(self, name, wave_name, kategorie='UnitTalk'):
        """Neuen Cue-Eintrag anhaengen, der auf einen Wave-Eintrag zeigt."""
        c = self.cue_liste()
        kennung = max((k.kennung for k in self._kinder(c)), default=0) + 1
        k = Knoten(kennung, [
            Eigenschaft(T_STR, b'Name', name.encode('latin-1')),
            Eigenschaft(T_STR, b'Category', kategorie.encode('latin-1')),
            Eigenschaft(T_U32, b'ChildCount', 1),
            Knoten(0, [
                Eigenschaft(T_STR, b'Name', wave_name.encode('latin-1')),
                Eigenschaft(T_STR, b'WaveBankName',
                            kategorie.encode('latin-1')),
            ]),
        ])
        c.inhalt.append(k)
        self._zaehler_setzen(c, len(self._kinder(c)))
        return k
