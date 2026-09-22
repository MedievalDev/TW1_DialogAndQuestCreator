"""Neue Aufnahmen an UnitTalk.xwb anhaengen, ohne 935 MB neu zu schreiben.

Der uebliche Weg waere, Metadaten einzuschieben - und weil ENTRYMETADATA VOR
den Wellendaten liegt, muesste dafuer die ganze Datei umgeschrieben werden.
Zwei Messungen machen das ueberfluessig:

  1. Zwischen dem Ende der Metadaten (209.236) und dem Beginn der Wellendaten
     (210.944) liegen 1.708 Nullbytes. Das sind 71 freie Plaetze zu je 24 Byte.
     Die Metadaten koennen also IN DIE LUECKE wachsen.
  2. ENTRYWAVEDATA ist die letzte Region und endet exakt am Dateiende
     (210.944 + 935.518.208 = 935.729.152). Neue Wellendaten kommen einfach
     dahinter.

Geaendert werden damit nur: 4 Byte Anzahl in BANKDATA, zwei Regionslaengen im
Kopf, die neuen Metadatensaetze in der Luecke - und der Anhang. Kein Byte
wird verschoben.

Was NICHT geht: vorhandene Eintraege uebernehmen. Von den 8.712 ist keiner
frei. Die 1.126, die an keinem einfachen Cue haengen, gehoeren zu 148
komplexen Sounds mit Variationslisten - den Bark-Pools des Helden. Jeder der
8.712 Eintraege wird genau einmal referenziert, es gibt weder Doppelung noch
Luecke.

Ausrichtung: BANKDATA nennt 2048, und alle 8.712 playOffsets sind ohne
Ausnahme durch 2048 teilbar. Die Bank wird gestreamt (Flag-Bit 0), die 2048
sind die Sektorgroesse fuers ungepufferte Lesen. Neue Daten muessen deshalb
auf einem Vielfachen beginnen UND aufgefuellt werden, sonst liest der letzte
Sektorzugriff ueber das Dateiende hinaus.
"""
import os
import shutil
import struct

REGIONEN = ['BANKDATA', 'ENTRYMETADATA', 'SEEKTABLES', 'ENTRYNAMES',
            'ENTRYWAVEDATA']
KOPF = 12 + 5 * 8          # Kennung, zwei Versionen, fuenf Regionen
EINTRAG = 24


class Xwb:
    """Wave-Bank zum Anhaengen. Arbeitet auf einer Kopie, nie am Original."""

    def __init__(self, pfad):
        self.pfad = pfad
        with open(pfad, 'rb') as f:
            k = f.read(KOPF)
            if k[:4] != b'WBND':
                raise ValueError(f'keine XACT-Wave-Bank: {k[:4]!r}')
            self.version, self.kopfversion = struct.unpack_from('<II', k, 4)
            self.regionen = {n: list(struct.unpack_from('<II', k, 12 + i * 8))
                             for i, n in enumerate(REGIONEN)}
            off, ln = self.regionen['BANKDATA']
            f.seek(off)
            bd = f.read(ln)
            self.flags, self.count = struct.unpack_from('<II', bd, 0)
            self.name = bd[8:72].split(b'\x00')[0].decode('latin-1')
            self.eintragsgroesse, self.namensgroesse, self.ausrichtung = \
                struct.unpack_from('<III', bd, 72)
        self.groesse = os.path.getsize(pfad)

    def luecke(self):
        """Freie Bytes zwischen Metadatenende und Beginn der Wellendaten."""
        mo, ml = self.regionen['ENTRYMETADATA']
        wo, _ = self.regionen['ENTRYWAVEDATA']
        return wo - (mo + ml)

    def platz(self):
        """Wie viele neue Eintraege in die Luecke passen."""
        return self.luecke() // EINTRAG

    def pruefen(self):
        """Die Annahmen nachrechnen, bevor geschrieben wird."""
        mo, ml = self.regionen['ENTRYMETADATA']
        wo, wl = self.regionen['ENTRYWAVEDATA']
        fehler = []
        if ml != self.count * EINTRAG:
            fehler.append(f'Metadaten {ml} passen nicht zu {self.count} '
                          f'Eintraegen a {EINTRAG}')
        if wo + wl != self.groesse:
            fehler.append(f'Wellendaten enden bei {wo + wl}, '
                          f'Datei bei {self.groesse}')
        if wl % self.ausrichtung:
            fehler.append(f'Laenge der Wellendaten {wl} ist kein Vielfaches '
                          f'von {self.ausrichtung}')
        with open(self.pfad, 'rb') as f:
            f.seek(mo + ml)
            if any(f.read(self.luecke())):
                fehler.append('die Luecke hinter den Metadaten ist nicht leer')
        return fehler

    def anhaengen(self, neue):
        """neue = [(rohdaten, formatwort, bloecke)] -> Liste der neuen Indizes.

        Schreibt in DIESE Datei. Sie muss eine Arbeitskopie sein.
        """
        fehler = self.pruefen()
        if fehler:
            raise ValueError('Wave-Bank passt nicht zu den Annahmen: '
                             + '; '.join(fehler))
        if len(neue) > self.platz():
            raise ValueError(f'{len(neue)} neue Eintraege, aber nur '
                             f'{self.platz()} passen in die Luecke')

        mo, ml = self.regionen['ENTRYMETADATA']
        wo, wl = self.regionen['ENTRYWAVEDATA']
        aus = self.ausrichtung
        indizes = []

        with open(self.pfad, 'r+b') as f:
            f.seek(0, os.SEEK_END)
            zeiger = wl                    # regionrelativ, nicht dateirelativ
            meta = bytearray()
            for roh, fmt, bloecke in neue:
                if zeiger % aus:
                    raise AssertionError('Schreibzeiger nicht ausgerichtet')
                # Dauer und Schleifenlaenge wie im Regelfall der Bank:
                # 7860 der 8712 Eintraege haben Dauer = n*128 + 1 bei
                # Schleifenlaenge n*128. Flags stehen in den unteren vier
                # Bit und sind bei allen 8712 null.
                schleife = bloecke * 128
                dauer = schleife + 1
                meta += struct.pack('<IIIIII', dauer << 4, fmt, zeiger,
                                    len(roh), 0, schleife)
                f.write(roh)
                fuell = (-len(roh)) % aus
                if fuell:
                    f.write(b'\0' * fuell)
                zeiger += len(roh) + fuell
                indizes.append(self.count + len(indizes))

            # Metadaten in die Luecke schreiben.
            f.seek(mo + ml)
            f.write(meta)

            neu_count = self.count + len(neue)
            neu_ml = ml + len(meta)
            neu_wl = zeiger

            # BANKDATA: Anzahl.
            f.seek(self.regionen['BANKDATA'][0] + 4)
            f.write(struct.pack('<I', neu_count))
            # Kopf: Laenge der Metadaten, Laenge der Wellendaten.
            f.seek(12 + 1 * 8 + 4)
            f.write(struct.pack('<I', neu_ml))
            f.seek(12 + 4 * 8 + 4)
            f.write(struct.pack('<I', neu_wl))
            # SEEKTABLES hat Laenge 0, sein Offset laege sonst mitten in den
            # gewachsenen Metadaten. Auf deren neues Ende setzen, damit die
            # Regionen widerspruchsfrei bleiben.
            f.seek(12 + 2 * 8)
            f.write(struct.pack('<II', mo + neu_ml, 0))

        self.count = neu_count
        self.regionen['ENTRYMETADATA'][1] = neu_ml
        self.regionen['ENTRYWAVEDATA'][1] = neu_wl
        self.regionen['SEEKTABLES'] = [mo + neu_ml, 0]
        self.groesse = os.path.getsize(self.pfad)
        return indizes


    def neu_schreiben(self, quelle, neue, blockgroesse=32 << 20, ziel=None):
        """Bank mit VERGROESSERTEM Metadatenblock neu schreiben.

        `ziel` trennt Lesen und Schreiben. Ohne das muss DIESES Objekt die
        unberuehrte Bank sein, denn Kopf, Anzahl und Metadaten kommen aus
        ihm, die Wellendaten dagegen aus `quelle`. Wer ein Objekt auf die
        bereits erweiterte Datei setzt und `quelle` auf die Sicherung, baut
        eine Bank, deren Metadaten 104 Eintraege mehr versprechen, als
        Wellendaten da sind - der Installer hat genau das getan.

        Sauber ist deshalb: Xwb auf die SICHERUNG, `ziel` auf die Spieldatei.

        Der Lueckentrick reicht nur fuer 71 zusaetzliche Eintraege. Wer mehr
        braucht, muss den Metadatenblock wirklich vergroessern - und weil er
        VOR den Wellendaten liegt, wandern die mit.

        Das ist weniger schlimm, als es klingt: playOffset ist
        REGIONRELATIV, nicht dateirelativ. Verschiebt sich der Anfang der
        Region, bleiben alle 8712 Offsets gueltig. Zu tun ist also nur:
        Kopf und Anzahl anpassen, Metadaten schreiben, auffuellen, und die
        Wellendaten unveraendert durchreichen.

        Geschrieben wird in Bloecken, damit nicht 935 MB im Speicher landen.
        """
        aus = self.ausrichtung
        alt_count = self.count
        mo, ml = self.regionen['ENTRYMETADATA']
        wo, wl = self.regionen['ENTRYWAVEDATA']

        neu_count = alt_count + len(neue)
        neu_ml = neu_count * EINTRAG
        neu_wo = (mo + neu_ml + aus - 1) // aus * aus

        with open(self.pfad, 'rb') as q:
            kopf = bytearray(q.read(KOPF))
            q.seek(self.regionen['BANKDATA'][0])
            bankdata = bytearray(q.read(self.regionen['BANKDATA'][1]))
            q.seek(mo)
            meta = bytearray(q.read(ml))

        struct.pack_into('<I', bankdata, 4, neu_count)
        # Regionen: Metadaten laenger, SEEKTABLES ans neue Ende, Wellendaten
        # an den neuen Anfang. Ihre Laenge waechst um den Anhang.
        struct.pack_into('<II', kopf, 12 + 1 * 8, mo, neu_ml)
        struct.pack_into('<II', kopf, 12 + 2 * 8, mo + neu_ml, 0)

        zeiger = wl
        for roh, fmt, bloecke in neue:
            schleife = bloecke * 128
            meta += struct.pack('<IIIIII', (schleife + 1) << 4, fmt, zeiger,
                                len(roh), 0, schleife)
            zeiger += len(roh) + ((-len(roh)) % aus)
        struct.pack_into('<II', kopf, 12 + 4 * 8, neu_wo, zeiger)

        ziel = ziel or self.pfad
        with open(quelle, 'rb') as q, open(ziel + '.neu', 'wb') as z:
            z.write(kopf)
            z.write(b'\0' * (self.regionen['BANKDATA'][0] - len(kopf)))
            z.write(bankdata)
            z.write(meta)
            z.write(b'\0' * (neu_wo - (mo + len(meta))))
            q.seek(wo)
            rest = wl
            while rest > 0:
                stueck = q.read(min(blockgroesse, rest))
                if not stueck:
                    break
                z.write(stueck)
                rest -= len(stueck)
            for roh, _fmt, _bl in neue:
                z.write(roh)
                fuell = (-len(roh)) % aus
                if fuell:
                    z.write(b'\0' * fuell)

        os.replace(ziel + '.neu', ziel)
        self.__init__(ziel)
        return list(range(alt_count, neu_count))


def arbeitskopie(quelle, ziel):
    """Kopie anlegen, falls noch keine da ist. Das Original bleibt heilig."""
    if not os.path.exists(ziel):
        os.makedirs(os.path.dirname(ziel), exist_ok=True)
        shutil.copy2(quelle, ziel)
    return ziel
