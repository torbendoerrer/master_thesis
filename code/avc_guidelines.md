# SAP AVC Syntax-Handbuch für Variantentabellen

WICHTIG: Du erstellst Tabellen IMMER nach folgendem AVC-Schema. Halte dich strikt an diese Muster!

## 1. Reiner Tabellenaufruf (Standard)
TABLE VC_TAB_DEIN_NAME (
  Merkmal_A = pc.Merkmal_A,
  Merkmal_B = pc.Merkmal_B,
  Ergebnis_Merkmal = pc.Ergebnis_Merkmal
)

## 2. Einzelne IF-Bedingung (Für Ausreißer außerhalb der Tabelle)
pc.Ergebnis_Merkmal = 'Wert' IF pc.Merkmal_A = '1' AND pc.Merkmal_B = '2'

## 3. Aggregation (Mehrere Werte mit gleicher Bedingung)
pc.Ergebnis_Merkmal IN ('Wert1', 'Wert2') IF pc.Merkmal_A = '1'

## ABSOLUTE VERBOTE (STRICT RULES):
- Eine Variantentabelle im SAP enthält NIEMALS Metadaten (wie 'description', 'precondition', 'code' oder Datentypen wie 'CHAR').
- Die Parameter im TABLE-Aufruf (in den Klammern) sind immer 'Spaltenname = pc.Merkmal'.
- Benutze NIEMALS SQL (kein SELECT, kein FROM, kein WHERE, kein OPTIONAL).
- Alle Zuweisungen und Vergleiche in Constraints müssen zwingend mit 'pc.' referenziert werden (z.B. pc.K40_FG_AF).