// Halter fuer den Raspberry Pi 4 an der Rueckseite des Bildschirms.
//
// Ersetzt die ausgelaserte Holzplatte: Er wird mit zwei M3-Schrauben in die
// beiden Gewinde des Bildschirms geschraubt (Abstand 75 mm, Gewinde nur 5 mm
// tief - also kurze Schrauben nehmen, M3 x 8 reicht). Der Pi sitzt auf vier
// angeformten Abstandshaltern, damit die Loetstellen unter der Platine frei
// bleiben.
//
// Offen und deshalb oben einstellbar: wie weit der Pi unter den Gewinden
// sitzen soll (PI_ABSTAND) und wie dick die Platte wird. Alles in Millimetern.
//
// Rendern und als STL sichern:  openscad -o pi-holder.stl pi-holder.scad

// ---- Was du anpassen kannst -------------------------------------------------
PLATTE_B      = 90;    // Breite der Platte, wie bei deiner Holzversion
PLATTE_D      = 4;     // Dicke der Platte
SCHIRM_LOCH   = 75;    // Abstand der beiden Gewinde im Bildschirm
SCHIRM_RAND   = 9;     // von der Oberkante der Platte bis zur Lochmitte
                       // gemessen hast du 5 - mit Senkung (Ø 6,4) blieben
                       // dann 1,8 mm Rand stehen. 9 gibt der Schraube Halt;
                       // die Platte ragt dafuer 4 mm weiter nach oben.
PI_ABSTAND    = 25;    // von der Lochmitte bis zur ersten Pi-Bohrung
STAND_H       = 5;     // Hoehe der Abstandshalter unter dem Pi
SCHRAUBE_M3   = 3.4;   // Durchgangsloch fuer M3
SCHRAUBE_M25  = 2.6;   // Kernloch fuer M2,5 - selbstschneidend in den Kunststoff
KABEL_SCHLITZ = true;  // Schlitz fuer das Kameraflachband

// ---- Feste Masse des Pi 4 ---------------------------------------------------
PI_X = 58;             // Lochabstand quer
PI_Y = 49;             // Lochabstand laengs
PI_RAND = 3.5;         // von der Platinenkante bis zur Lochmitte

PLATTE_H = SCHIRM_RAND + PI_ABSTAND + PI_Y + 14;

module abstandshalter() {
    difference() {
        cylinder(h = STAND_H, d = 7, $fn = 32);
        translate([0, 0, -0.1])
            cylinder(h = STAND_H + 0.2, d = SCHRAUBE_M25, $fn = 24);
    }
}

module platte() {
    difference() {
        // Grundplatte mit gerundeten Ecken
        hull() for (x = [6, PLATTE_B - 6], y = [6, PLATTE_H - 6])
            translate([x, y, 0]) cylinder(h = PLATTE_D, d = 12, $fn = 32);

        // Die beiden Schrauben in den Bildschirm
        for (dx = [-SCHIRM_LOCH / 2, SCHIRM_LOCH / 2])
            translate([PLATTE_B / 2 + dx, PLATTE_H - SCHIRM_RAND, -0.1]) {
                cylinder(h = PLATTE_D + 0.2, d = SCHRAUBE_M3, $fn = 32);
                // Senkung, damit der Schraubenkopf nicht auftraegt
                translate([0, 0, PLATTE_D - 1.8])
                    cylinder(h = 1.9, d1 = SCHRAUBE_M3, d2 = 6.4, $fn = 32);
            }

        // Schlitz fuer das Kameraflachband
        if (KABEL_SCHLITZ)
            translate([PLATTE_B / 2 - 9, 8, -0.1])
                cube([18, 3.5, PLATTE_D + 0.2]);
    }
}

module halter() {
    platte();
    // Vier Abstandshalter im Lochbild des Pi, mittig und unter den Schrauben
    pi_y0 = PLATTE_H - SCHIRM_RAND - PI_ABSTAND - PI_Y;
    for (dx = [0, PI_X], dy = [0, PI_Y])
        translate([(PLATTE_B - PI_X) / 2 + dx, pi_y0 + dy, PLATTE_D])
            abstandshalter();
}

halter();

// Hinweis zum Drucken: flach auf die Platte legen, 3 Perimeter, 25 % Fuellung.
// PETG oder PLA. Stuetzen braucht das Teil nicht.
