# Aktienfinder – Version 1

Browserbasierter Prototyp für ein manuelles Aktien-Screening.

## Enthalten
- Änderbare Standardfilter: Kurspotenzial 20 %, Marktkapitalisierung 100 Mio. USD, mindestens 3 Analysten-Kursziele, maximal 90 Tage.
- Mean und Median der individuellen Analystenkursziele; Potenzial wird anhand des Mean berechnet.
- Anzeige von ISIN, Land, Branche, Kurs, Marktkapitalisierung, Analystenzahl, Kurszielalter und Datenquellen.
- CSV-Import mit Einzelkursziel-Daten.
- Optionaler TargetWatch-API-Zugang.
- Export der Ergebnisse als echte Excel-Datei (.xlsx).

## Wichtige Einschränkung der Version 1
Ein belastbarer, kostenloser und weltweiter Datensatz mit individuellen Kurszielen, Analystenhäusern und Stichtagen ist nicht allgemein verfügbar. TargetWatch dokumentiert eine kostenlose API, deren Aktienuniversum aber nicht den gesamten Weltmarkt abdeckt und deren Free-Zugang limitiert ist. Deshalb unterstützt V1:
1. TargetWatch für dort abgedeckte Aktien (API-Key erforderlich).
2. CSV-Import für zusätzliche Märkte, wenn die Einzelkursziel-Daten vorliegen.
3. Yahoo Finance/yfinance nur für Kurs, Marktkapitalisierung (mit FX-Umrechnung, sofern verfügbar) und Stammdaten – nicht als Ersatz für die Zahl der Kursziel-Analysten.

Aktien werden nur als qualifiziert markiert, wenn die Zahl der eindeutigen Kursziel-Analysten, das Kurszielalter, das Kurspotenzial, die Marktkapitalisierung und die Währungsübereinstimmung prüfbar sind. Fehlende Daten werden nicht geschätzt.

## CSV-Format
Pflichtspalten:
`ticker,target_date,analyst,price_target,currency`

Optionale Spalten:
`isin,company,country,sector`

Jede Zeile steht für ein einzelnes Analystenkursziel.

## Lokal starten (nur zum Entwickeln)
```bash
pip install -r requirements.txt
streamlit run app.py
```

Für die spätere Nutzung auf jedem PC ohne lokale Installation kann die App über Streamlit Community Cloud veröffentlicht werden.

## Veröffentlichung
1. ZIP entpacken.
2. Dateien in ein GitHub-Repository hochladen.
3. Bei https://share.streamlit.io mit GitHub anmelden.
4. „Create app“ auswählen, Repository und `app.py` auswählen, dann „Deploy“.
5. Die erzeugte `*.streamlit.app`-Adresse kann im Browser auf PC, Mac und Tablet geöffnet werden.

Die Veröffentlichung erfordert ein eigenes GitHub- und Streamlit-Konto und muss vom Kontoinhaber bestätigt werden.
