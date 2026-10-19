/* [Layout] */
// Select assembled view or layout for 3D printing
layout = "printing"; // [assembled, printing]

/* [TV Dimensions] */
tv_radius = 70;       
wall = 3;   
base_z = -55; // Flat bottom at Z=-55 gives a stable base

/* [Power Button Fit] */
// Hole for the switch stem inside the button cap
power_hole_diameter = 3;   // [2:0.1:5]
// How deep the stem hole goes into the cap from its underside
power_hole_depth = 3;      // [1:0.5:6]

/* [Volume Knob Fit] */
// Widened outer part of the case hole that the knob tube drops into
knob_recess_diameter = 11.8; // [9:0.1:14]
// Depth of the widened part, measured from the outer case surface
knob_recess_depth = 3.5;     // [2:0.25:5]
// Tube on the knob that reaches down onto the trimmer pot
tube_outer_diameter = 11.2;  // [9:0.1:13]
// Inner bore that seats over the trimmer body; increase if too tight
tube_inner_diameter = 8.5;   // [7:0.1:10]
// How far the tube extends below the knob base
tube_length = 3;             // [2:0.5:5]

/* [Colors] */
body_color = "Teal";
accent_color = "Silver";
screen_color = "DarkSlateGray";
$fn = 64;

// --- Helper Functions ---
module sphere_pos(yaw, pitch, radius) {
    rotate([0, 0, yaw])
    rotate([pitch, 0, 0])
    translate([0, -radius, 0])
    rotate([90, 0, 0]) 
    children();
}

// --- Base Shapes ---
module outer_shape() {
    difference() {
        sphere(tv_radius, $fn=100);
        translate([0, 0, -500 + base_z]) cube(1000, center=true);
    }
}

module inner_shape() {
    difference() {
        sphere(tv_radius - wall, $fn=100);
        translate([0, 0, -500 + base_z + wall]) cube(1000, center=true);
    }
}

// --- Front Case ---
module front_case() {
    difference() {
        union() {
            // STRICT MATHEMATICAL INTERSECTION
            intersection() {
                outer_shape();
                
                union() {
                    // Main hollow shell (3mm wall)
                    difference() {
                        outer_shape();
                        inner_shape();
                    }
                    
                    // Bezel Funnel Body (Fuses perfectly with the front wall)
                    // Thickness is 25mm to support the 7mm deep pocket (Spans Y=-45 to Y=-70)
                    translate([0, -57.5, 5]) cube([85, 25, 65], center=true); 
                    
                    // Solid filler blocks to reinforce the button pockets 
                    // TOP (Volume): Low 10mm block (Z=61 to Z=71, protrudes exactly 6mm inside to support the 5mm slot)
                    sphere_pos(48, 15, 0) translate([0, 0, 61]) cylinder(d=22, h=10); 
                    // BOTTOM (Power / Mikrik): Low 14mm block (Z=56 to Z=70, protrudes exactly 11mm inside)
                    sphere_pos(48, -15, 0) translate([0, 0, 63]) cylinder(d=20, h=14, center=true); 
                    
                    // Screw bosses extending deeply from the split plane (Y=0) to the front wall (Y=-50)
                    // Added massive triangular ribs (gussets) to prevent them from snapping during print/assembly!
                    for(x=[-42, 42], z=[-35, 35]) {
                        hull() {
                            translate([x, 0, z]) rotate([90,0,0]) cylinder(d=8, h=50);
                            translate([x + sign(x)*12, 0, z]) rotate([90,0,0]) cylinder(d=4, h=50);
                        }
                    }
                }
            }
            
            // Floor standoffs for PAM8302 Amp (Completely removed)
            
            // Interlocking lip
            rotate([-90,0,0]) 
            difference() { 
                cylinder(r=tv_radius - wall, h=2, $fn=100); 
                cylinder(r=tv_radius - wall - 1.5, h=3, center=true, $fn=100); 
            }
        }
        
        // --- SUBTRACTIONS ---
        
        // Cut the back half completely off
        translate([0, 500, 0]) cube(1000, center=true); 
        
        // 1. VIEWING WINDOW (Starts exactly at Y=-52)
        hull() {
            translate([0, -52, 5.5]) cube([57, 0.1, 43], center=true); 
            translate([0, -80, 5.5]) cube([75, 0.1, 55], center=true); 
        }
        
        // 2. Clear out the inside cavity for the screen PCB (Exactly 70x52, Y=0 to Y=-52)
        // This single, clean cut from Y=0 to Y=-52 completely clears the pocket and 
        // creates an exact 7mm deep flat-bottomed recess in the Y=-45 front wall. 
        // (The shelf has been 100% removed, leaving the entire area completely open for cables!)
        translate([0, -26, 5]) cube([70, 52, 52], center=true); 
        
        // 3. Display specific recess
        translate([0, -45.5, 5]) cube([58.5, 3, 43.5], center=true); 
        
        // 4. Pockets & Internal Slots for Knobs
        
        // --- Volume Dial (TOP: pitch = 15) ---
        // Through hole in the case made exactly 8.8mm to perfectly fit the 8.3mm collar!
        sphere_pos(48, 15, 0) translate([0, 0, 40]) cylinder(d=8.8, h=35); 
        // Widened outer counterbore: the knob tube drops in here and grips the trimmer
        // (floor sits knob_recess_depth below the outer surface at R=70)
        sphere_pos(48, 15, 0) translate([0, 0, 70 - knob_recess_depth]) cylinder(d=knob_recess_diameter, h=15);
        // 10.2x10.2x5mm square slot for gluing the 10x10x5mm potentiometer body (Z=61 to Z=66, 100% open from inside!)
        sphere_pos(48, 15, 0) translate([0, 0, 63.5]) cube([10.2, 10.2, 5.1], center=true);
        
        // --- Power Button (BOTTOM: pitch = -15) ---
        // Outer pocket for the printed button head (floor at R=64, depth 6mm - button is sunk 3mm deeper!)
        sphere_pos(48, -15, 0) translate([0, 0, 64]) cylinder(d=14, h=15); 
        // 4.2x4.2mm square hole for the 4mm switch stem to pass through the EXACTLY 1mm thick wall (Z=63 to 64)
        sphere_pos(48, -15, 0) translate([0, 0, 63.5]) cube([4.2, 4.2, 1.2], center=true); 
        // Internal 7.2x7.2x7mm slot for gluing the 7x7x7mm switch body (Z=56 to Z=63, 100% open from inside!)
        sphere_pos(48, -15, 0) translate([0, 0, 56.5]) cube([7.2, 7.2, 13], center=true);
        
        // 5. Screw boss pilot holes (threaded side for self-tapping screws)
        for(x=[-42, 42], z=[-35, 35]) {
            translate([x, 1, z]) rotate([90,0,0]) cylinder(d=2.5, h=25);
        }
    }
}

// --- Back Case ---
module back_case() {
    difference() {
        union() {
            // STRICT MATHEMATICAL INTERSECTION
            intersection() {
                outer_shape();
                
                union() {
                    // Main hollow shell
                    difference() {
                        outer_shape();
                        inner_shape();
                    }
                    
                    // Solid speaker mount block for gluing
                    // Extended h=50 (starting at Y=30) so it fuses completely with the back wall (no gaps/internal layers!)
                    translate([0, 30, 0]) rotate([-90,0,0]) cylinder(d=83, h=50);
                    
                    // Back screw bosses (fused solidly to the shell wall with reinforcing ribs)
                    for(x=[-42, 42], z=[-35, 35]) {
                        hull() {
                            translate([x, 0, z]) rotate([-90,0,0]) cylinder(d=8, h=50);
                            translate([x + sign(x)*12, 0, z]) rotate([-90,0,0]) cylinder(d=4, h=50);
                        }
                    }
                }
            }
        }
        
        // --- SUBTRACTIONS ---
        translate([0, -500, 0]) cube(1000, center=true); 
        
        // 1. Speaker Grille Slots (A beautiful, bold 2D grid of 4.5mm holes for maximum sound)
        for(x=[-28:8:28], z=[-28:8:28]) {
            if (x*x + z*z < 34*34) { 
                translate([x, -10, z]) rotate([-90,0,0]) cylinder(d=4.5, h=120);
            }
        }
        
        // 2. Speaker Pocket (77.5mm for exactly 3" speaker drop-in and glue)
        translate([0, 0, 0]) rotate([-90,0,0]) cylinder(d=77.5, h=52);
        
        // 2b. Cone relief pocket
        translate([0, 0, 0]) rotate([-90,0,0]) cylinder(d=72, h=56);
        
        // 3. Screw boss holes (Clearance and counterbores from the back)
        for(x=[-42, 42], z=[-35, 35]) {
            translate([x, -5, z]) rotate([-90,0,0]) cylinder(d=3.2, h=30); 
            translate([x, 15, z]) rotate([-90,0,0]) cylinder(d=6.5, h=70);  
        }
        
        // 4. Micro USB port opening
        translate([0, 60, -45]) cube([14, 30, 7], center=true);
        
        // 5. Antenna mounting holes
        sphere_pos(45, -110, 0) translate([0,0,50]) cylinder(d=5.5, h=30);
        sphere_pos(-45, -110, 0) translate([0,0,50]) cylinder(d=5.5, h=30);
    }
}

// --- Accessories ---
module knob_vol() {
    // Volume knob: flat on top, with a tube underneath that drops through the
    // widened case recess and seats directly over the trimmer pot body.
    difference() {
        union() {
            cylinder(d=16, h=10); 
            for(i=[0:15:359]) {
                rotate([0,0,i]) translate([8, 0, 0]) cylinder(r=0.8, h=10, $fn=16);
            }
            // Grip tube: reaches down into the widened recess, onto the trimmer
            translate([0,0,-tube_length]) cylinder(d=tube_outer_diameter, h=tube_length + 0.01);
        }
        // Bore that slides over the trimmer body (extends 2mm up into the head
        // to swallow the 1.5mm of the pot that protrudes above the case surface)
        translate([0,0,-tube_length - 0.1]) cylinder(d=tube_inner_diameter, h=tube_length + 2.1);
        // Shaft connector hole (exactly 6.66mm, up to 3mm below the flat top)
        translate([0,0,-tube_length]) cylinder(d=6.66, h=tube_length + 7); 
    }
}

module knob_power() {
    // Printed button cap for the power switch.
    // Stem hole: exactly power_hole_diameter wide and power_hole_depth deep.
    difference() {
        cylinder(d=11, h=8);
        translate([0,0,-1]) cylinder(d=power_hole_diameter, h=power_hole_depth + 1);
    }
}

module antenna() {
    cylinder(d=4, h=50);
    translate([0, 0, 50]) sphere(d=10);
}

// --- Render Layout ---
if (layout == "assembled") {
    color(body_color) front_case();
    color(body_color) back_case();
    
    // Positioned in their final resting depth
    color(accent_color) sphere_pos(48, 15, 0) translate([0,0,70]) knob_vol();
    color(accent_color) sphere_pos(48, -15, 0) translate([0,0,64]) knob_power();
    
    color(accent_color) sphere_pos(45, -110, 0) translate([0,0,60]) antenna();
    color(accent_color) sphere_pos(-45, -110, 0) translate([0,0,60]) antenna();
    
} else if (layout == "printing") {
    translate([-80, 0, 0]) rotate([-90, 0, 0]) color(body_color) front_case();
    translate([ 80, 0, 0]) rotate([ 90, 0, 0]) color(body_color) back_case();
    
    // Knobs flipped upside down so they print perfectly flat without supports
    translate([-25, 75, 10]) rotate([180, 0, 0]) color(accent_color) knob_vol();
    translate([ 25, 75, 8]) rotate([180, 0, 0]) color(accent_color) knob_power();
    
    translate([-40, 90, 2]) color(accent_color) rotate([0, 90, 0]) antenna();
    translate([ 40, 90, 2]) color(accent_color) rotate([0, 90, 0]) antenna();
}
