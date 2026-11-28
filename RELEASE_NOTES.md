# Thonny SE 1.2.0

## Improvements

- **Adjust diagram design:** Structograms and UML diagrams can use more compact spacing and stronger lines. Higher design settings use bold text. The design also applies to graphic exports; the separate zoom control only changes the screen view.
- **Recognise relationships more easily:** Arrowheads, triangles and diamonds have more consistent sizes. Their attachment points account for the borders of class cards, keeping the symbols clear even with stronger lines.
- **Organise the object bench:** Drag object cards to reorder them, collapse or expand entire cards, and remove objects from the bench. Use the context menu to instantiate further objects from the UML classes you have run.
- **See connections and changes:** Selecting a nested object highlights its other appearances. Selecting a list also highlights the objects it contains, even when the list is collapsed. Changed values briefly light up.
- **Keep working with returned objects:** Objects returned by methods can be added to the object bench under their own names and explored further. This does not call the method again.
- **Work more smoothly with many objects:** Drawing and selection on the object bench are faster. Switching selection takes much less time when many object cards are present.
- **Recognise actions more easily:** New icons identify actions including adding classes, attributes, methods and comments, instantiating objects, navigating to code and detecting relationships automatically.
- **Documentation:** The README and manual have been updated in German and English. New images show diagram design and the extended object bench features.

- **Edit classes more easily:** Press Enter to edit the header of the selected class. Empty compartments show subtle prompts for adding attributes and methods. The lower navigation arrow becomes active only when the inputs allow the method to be created.
- **Add base classes directly:** Entering an unknown class name under “inherits from” creates the base class and its inheritance arrow when confirmed.

## Bug fixes

- Optional parameters display their default values correctly even when the Windows theme provides empty or numeric padding values.
- Very long method names without parameters no longer block the call dialog through repeated layout changes on small screens.
- UML cards retain the same dimensions when zooming as in graphic exports.
- Access modifiers before expandable references on the object bench are no longer covered by the arrow area.
- Right-clicking nested lists and their contents now also opens the context menu of the enclosing object card.

- The Close button in the About dialog provides more room to prevent its label from being clipped on Windows.
- Manually added or edited constructors appear before the other methods.
- Completely empty parameter rows in the class editor no longer create required parameters.
- After adding constructor parameters from the bottom input row, the down arrow returns to the input row for a new method.
- UML class editor inputs and controls retain their size when zooming or changing diagram design.
- The macOS pinch gesture also reaches the diagram over open UML editor input fields.
- An error when refreshing the display with an open class editor has been fixed.

---

# Thonny SE 1.2.0

## Verbesserungen

- **Diagramme passend darstellen:** Struktogramme und UML-Diagramme lassen sich kompakter und mit kräftigeren Linien darstellen. Bei höherer Gestaltungsstufe wird die Schrift fett. Die Gestaltung gilt auch für den Grafikexport; der separate Zoom verändert nur die Bildschirmansicht.
- **Beziehungen klarer erkennen:** Pfeilspitzen, Dreiecke und Rauten haben eine einheitlichere Größe. Ihre Anschlüsse berücksichtigen die Rahmenstärke der Klassenkarten, damit die Symbole auch bei kräftigen Linien gut erkennbar bleiben.
- **Objektbank ordnen:** Objektkarten lassen sich verschieben und vollständig ein- oder ausklappen. Objekte können aus der Objektbank entfernt werden. Über das Kontextmenü lassen sich weitere Objekte aus den ausgeführten UML-Klassen instanziieren.
- **Zusammenhänge und Änderungen sehen:** Die Auswahl eines Unterobjekts hebt die zugehörigen Objektdarstellungen hervor. Bei Listen werden auch die enthaltenen Objekte markiert, selbst wenn die Liste zugeklappt ist. Geänderte Werte leuchten kurz auf.
- **Mit Rückgaben weiterarbeiten:** Von Methoden zurückgegebene Objekte können unter einem eigenen Namen in die Objektbank übernommen und weiter untersucht werden. Die Methode wird dafür nicht erneut aufgerufen.
- **Flüssiger mit vielen Objekten arbeiten:** Die Darstellung und Auswahl in der Objektbank wurden beschleunigt. Besonders der Auswahlwechsel benötigt bei vielen Objektkarten deutlich weniger Zeit.
- **Aktionen leichter erkennen:** Neue Symbole kennzeichnen unter anderem das Hinzufügen von Klassen, Attributen, Methoden und Kommentaren, die Objektinstanziierung, den Sprung zum Code und die automatische Beziehungserkennung.
- **Dokumentation:** README und Manual wurden auf Deutsch und Englisch ergänzt. Neue Bilder zeigen die Diagrammgestaltung und die erweiterten Möglichkeiten der Objektbank.

- **Klassen einfacher bearbeiten:** Enter öffnet den Klassenkopf einer ausgewählten Klasse. Leere Bereiche zeigen dezente Hinweise zum Hinzufügen von Attributen und Methoden. Der untere Navigationspfeil wird erst aktiv, wenn die Eingaben das Anlegen der Methode erlauben.
- **Basisklassen direkt ergänzen:** Wird unter „erbt von“ ein noch unbekannter Klassenname eingetragen, werden beim Bestätigen die Basisklasse und der Vererbungspfeil angelegt.

## Fehlerbehebungen

- Optionale Parameter zeigen ihre Standardwerte auch dann korrekt an, wenn das Windows-Theme leere oder numerische Abstandsangaben liefert.
- Sehr lange Methodennamen ohne Parameter können den Aufrufdialog bei kleinen Bildschirmauflösungen nicht mehr durch eine fortlaufende Layoutänderung blockieren.
- UML-Karten behalten beim Zoomen dieselben Maße wie im Grafikexport.
- Zugriffsmodifikatoren vor aufklappbaren Referenzen in der Objektbank werden nicht mehr vom Pfeilbereich verdeckt.
- Rechtsklick auf verschachtelte Listen und deren Inhalte öffnet nun ebenfalls das Kontextmenü der zugehörigen Objektkarte.

- Der Schließen-Button im Info-Dialog bietet mehr Platz, damit seine Beschriftung unter Windows nicht abgeschnitten wird.
- Manuell ergänzte oder bearbeitete Konstruktoren stehen vor den übrigen Methoden.
- Vollständig leere Parameterzeilen im Klasseneditor erzeugen keine erforderlichen Parameter mehr.
- Nach Ergänzen eines Konstruktors aus der unteren Eingabezeile führt der Abwärtspfeil zur Eingabe einer neuen Methode.
- Die Eingabefelder und Bedienelemente im UML-Klasseneditor behalten beim Zoomen und Ändern der Diagrammgestaltung ihre Größe.
- Die Zwei-Finger-Zoomgeste auf macOS erreicht das Diagramm auch über geöffneten UML-Eingabefeldern.
- Ein Fehler beim Aktualisieren der Anzeige mit geöffnetem Klasseneditor wurde behoben.
