# Demo_RC2-IFC



## Klassifizierung
WebApp zur klassifizierung (IfcClassification) der Elemente der IFC Datei manuell oder automatisch mittels Regeln.
[ifcclassify.com](https://ifcclassify.com/)
Die App ist open-source:
[github/louistrue/ifc-classifier](https://github.com/louistrue/ifc-classifier)




### Laden der IFC Datei (nirgendwo hochgeladen, bleibt am Rechner)

<img width="500" height="366" alt="image" src="https://github.com/AIztok/Demo_RC2-IFC/blob/main/Figures/c_1.png" />

### Importieren der Klassifizierung

<img width="500" height="366" alt="image" src="https://github.com/AIztok/Demo_RC2-IFC/blob/main/Figures/c_2.png" />

Beispiel einer Excel mit der Klassifizierung gem. Standardelementekatalog:
[Excel mit Regeln](https://github.com/AIztok/Demo_RC2-IFC/blob/main/ifcclassifier/classifications_RC2.xlsx)

<img width="500" height="366" alt="image" src="https://github.com/AIztok/Demo_RC2-IFC/blob/main/Figures/c_3.png" />

<img width="500" height="366" alt="image" src="https://github.com/AIztok/Demo_RC2-IFC/blob/main/Figures/c_3_.png" />

### Klassifizieren nach Regeln

Die Klassifizierung kann auch über Regeln erfolgen

<img width="500" height="366" alt="image" src="https://github.com/AIztok/Demo_RC2-IFC/blob/main/Figures/c_4.png" />

Beispiel einer Excel mit der Regel alle Elemente der IfcClass = IfcRailing als Geländer Klassifizieren:
[Excel mit Regeln](https://github.com/AIztok/Demo_RC2-IFC/blob/main/ifcclassifier/regeln_RC2.xlsx)

Regel ausführen:

<img width="500" height="366" alt="image" src="https://github.com/AIztok/Demo_RC2-IFC/blob/main/Figures/c_5.png" />

<img width="500" height="366" alt="image" src="https://github.com/AIztok/Demo_RC2-IFC/blob/main/Figures/c_6.png" />

### IFC mit Klassifizierung exportieren
IFC Export:

<img width="500" height="366" alt="image" src="https://github.com/AIztok/Demo_RC2-IFC/blob/main/Figures/c_7.png" />

Metadatenfelder bearbeiten:

<img width="500" height="366" alt="image" src="https://github.com/AIztok/Demo_RC2-IFC/blob/main/Figures/c_8.png" />

Exportieren:
<img width="1000" height="366" alt="image" src="https://github.com/AIztok/Demo_RC2-IFC/blob/main/Figures/c_9.png" />

Beispiel der Klassifizierung im IFC:

<img width="1000" height="366" alt="image" src="https://github.com/AIztok/Demo_RC2-IFC/blob/main/Figures/c_10.png" />

## Lesen und Schreiben IFC

Daten lesen aus der IFC Datei und z.B. speichern in CSV Format (bzw. in RC2 anzeigen in Tabellenformat):

Daten bearbieten, hier beispielhaft:
- Tabelle wo die Klassifizierung als Positions und Menge übernommen - kann aber manuell geändert werden
- speichern einer IFC Datei mit ergänzten OEBBset_RC2

https://demo-rc2-ifc.streamlit.app/

### IFC Datei in die App laden
IFC Datei in die App laden:

<img width="1000" height="366" alt="image" src="https://github.com/AIztok/Demo_RC2-IFC/blob/main/Figures/1.png" />

Wenn Datei geladen:

<img width="1000" height="366" alt="image" src="https://github.com/AIztok/Demo_RC2-IFC/blob/main/Figures/2.png" />

### Quantity take-off
Automatische Berechnung der Mengen:
- GrossArea (Brutto Fläche)
- GrossVolume (Brutto Volumen)
- Length (maximale Länge eines Kastens 
und schreiben der Ergebnisse in den PSet Qto_"IfcClass"BaseQuantities der Ifc Datei


<img width="1000" height="366" alt="image" src="https://github.com/AIztok/Demo_RC2-IFC/blob/main/Figures/3.png" />

Nach Berechnung der Werte kann die adaptierte IFC gespeichert werden:

<img width="1000" height="366" alt="image" src="https://github.com/AIztok/Demo_RC2-IFC/blob/main/Figures/4.png" />

Beispiel der gespeicherten Mengen im IFC:

<img width="1000" height="366" alt="image" src="https://github.com/AIztok/Demo_RC2-IFC/blob/main/Figures/5.png" />

### CSV Export - Daten lesen

Es werden folgende Daten gelesen:
Guid, class, name, classifications, quantities and oebbset_semantik_topologie

<img width="1000" height="366" alt="image" src="https://github.com/AIztok/Demo_RC2-IFC/blob/main/Figures/6.png" />

De Tabelle wird angezeigt und kann als csv gespeichert werden:
<img width="1000" height="366" alt="image" src="https://github.com/AIztok/Demo_RC2-IFC/blob/main/Figures/7.png" />

### PSet RC2
Eine bearbeitbare Tabelle wird erstellt, die Klassifizierung wird zur Demostration mit Volumen gefüllt, kann aber manuell geändert werden

<img width="1000" height="366" alt="image" src="https://github.com/AIztok/Demo_RC2-IFC/blob/main/Figures/7.png" />

Tabelle erzeugen:

<img width="1000" height="366" alt="image" src="https://github.com/AIztok/Demo_RC2-IFC/blob/main/Figures/8.png" />

Tabelle erzeugt:

<img width="1000" height="366" alt="image" src="https://github.com/AIztok/Demo_RC2-IFC/blob/main/Figures/9.png" />

Tabelle kann bearbeitet werden:

<img width="1000" height="366" alt="image" src="https://github.com/AIztok/Demo_RC2-IFC/blob/main/Figures/10.png" />

IFC Datei speichern:

<img width="1000" height="366" alt="image" src="https://github.com/AIztok/Demo_RC2-IFC/blob/main/Figures/11.png" />

Beispiel der IFC Datei mit dem OEBBset_RC2:

<img width="1000" height="366" alt="image" src="https://github.com/AIztok/Demo_RC2-IFC/blob/main/Figures/12.png" />
