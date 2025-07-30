# Demo_RC2-IFC



## Klassifizierung
WebApp zur klassifizierung (IfcClassification) der Elemente der IFC Datei manuell oder automatisch mittels Regeln.
[ifcclassify.com](https://ifcclassify.com/)
Die App ist open-source:
[github/louistrue/ifc-classifier](https://github.com/louistrue/ifc-classifier)




Laden der IFC Datei (nirgendwo hochgeladen, bleibt am Rechner):
<img width="1546" height="366" alt="image" src="https://github.com/AIztok/Demo_RC2-IFC/blob/main/Figures/c_1.png" />

Importieren der Klassifizierung:
<img width="1546" height="366" alt="image" src="https://github.com/AIztok/Demo_RC2-IFC/blob/main/Figures/c_2.png" />


<img width="1546" height="366" alt="image" src="https://github.com/AIztok/Demo_RC2-IFC/blob/main/Figures/c_3.png" />

## Lesen und Schreiben IFC

Daten lesen aus der IFC Datei und z.B. speichern in CSV Format (bzw. in RC2 anzeigen in Tabellenformat):

Daten bearbieten, hier beispielhaft:
- Tabelle wo die Klassifizierung als Positions und Menge übernommen - kann aber manuell geändert werden
- speichern einer IFC Datei mit ergänzten OEBBset_RC2

https://demo-rc2-ifc.streamlit.app/

### IFC Datei in die App laden
IFC Datei in die App laden:
<img width="1546" height="366" alt="image" src="https://github.com/AIztok/Demo_RC2-IFC/blob/main/Figures/1.png" />

Wenn Datei geladen:
<img width="1546" height="366" alt="image" src="https://github.com/AIztok/Demo_RC2-IFC/blob/main/Figures/2.png" />

### Quantity take-off
Automatische Berechnung der Mengen:
- GrossArea (Brutto Fläche)
- GrossVolume (Brutto Volumen)
- Length (maximale Länge eines Kastens 
und schreiben der Ergebnisse in den PSet Qto_"IfcClass"BaseQuantities der Ifc Datei


<img width="1546" height="366" alt="image" src="https://github.com/AIztok/Demo_RC2-IFC/blob/main/Figures/3.png" />

Nach Berechnung der Werte kann die adaptierte IFC gespeichert werden:
<img width="1546" height="366" alt="image" src="https://github.com/AIztok/Demo_RC2-IFC/blob/main/Figures/4.png" />

Beispiel der gespeicherten Mengen im IFC:
<img width="1546" height="366" alt="image" src="https://github.com/AIztok/Demo_RC2-IFC/blob/main/Figures/5.png" />

### CSV Export - Daten lesen



### PSet RC2



