Kundenspezifisches

Umgang mit "specified dummy"

Bedeutung: Das Merkmal dummy wird in dieser Systemlandschaft zur Laufzeit niemals bewertet. Eine Bedingung wie specified dummy ist eine historische Altlast (Workaround aus LO-VC Zeiten), um einen Wert hart zu deaktivieren.

Handlungsanweisung: Werte (Codes), die in ihrer Syntax von specified dummy abhängig sind, werden in der Realität niemals gezogen.

Aktion für die Migration: 1. Nimm diesen Code und seine restlichen Bedingungen NICHT mit in die finale Variantentabelle auf. Er wird komplett ausgelassen.
2. Dokumentiere im Text der "Herleitung" explizit, dass dieser Wert aufgrund der "specified dummy"-Regel ignoriert und aussortiert wurde, damit die nachfolgenden Entwickler den Grund nachvollziehen können.