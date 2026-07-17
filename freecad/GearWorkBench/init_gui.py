# ***************************************************************************
# *                                                                         *
# *   Copyright (c) 2025                                                    *
# *   Chris Bruner                                                          *
# *                                                                         *
# *   This program is free software; you can redistribute it and/or modify  *
# *   it under the terms of the GNU Lesser General Public License (LGPL)    *
# *   as published by the Free Software Foundation; either version 2 of     *
# *   the License, or (at your option) any later version.                   *
# *   for detail see the LICENCE text file.                                 *
# *                                                                         *
# *   This program is distributed in the hope that it will be useful,       *
# *   but WITHOUT ANY WARRANTY; without even the implied warranty of        *
# *   MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the         *
# *   GNU Library General Public License for more details.                  *
# *                                                                         *
# *   You should have received a copy of the GNU Library General Public     *
# *   License along with this program; if not, write to the Free Software   *
# *   Foundation, Inc., 59 Temple Place, Suite 330, Boston, MA  02111-1307  *
# *   USA                                                                   *
# *                                                                         *
# ***************************************************************************

import os
import FreeCAD
import FreeCADGui
from . import gearMath

Log = FreeCAD.Console.PrintLog
Err = FreeCAD.Console.PrintError
from . import genericGear  # Generic gear framework (spur, helical, herringbone)
from . import genericInternalGear  # Generic internal gear framework
from . import gearPositioning  # Gear positioning tool
from . import planetaryGearCreator  # Planetary gear system creator
from . import cycloidGearCreator  # Cycloidal gearbox creator
from . import rackGear  # Import rack gear module
from . import cycloidGear  # Import cycloid gear module
from . import cycloidRack  # Import cycloid rack module
from . import bevelGear  # Import bevel gear module
from . import crownGear  # Import crown gear module
from . import wormGear  # Import worm gear module
from . import globoidWormGear  # Import globoid worm gear module
from . import hypoidGear  # Import hypoid gear module
from . import screwGear  # Import screw gear module
from . import nonCircularGear  # Import non-circular gear module
from . import genevaWheel  # Import Geneva wheel (Maltese cross) module
from . import gearStack  # Import gear stack module
from . import gearAxles  # Import gear axles module
from . import gearLog  # Action logger for test documentation

smWBpath = os.path.dirname(gearMath.__file__)
smWB_icons_path = os.path.join(smWBpath, "icons")
global main_Gear_Icon
main_Gear_Icon = os.path.join(smWB_icons_path, "gearWorkbench.svg")


class GearWorkBenchWB(FreeCADGui.Workbench):
    """Gear Design Workbench - Parametric gears for 3D printing"""

    MenuText = "GearWorkBench"
    ToolTip = (
        "Parametric gear designer for 3D printing (spur, helical, rack, bevel, etc.)"
    )
    Icon = main_Gear_Icon

    def Initialize(self):
        """This function is executed when FreeCAD starts"""
        try:
            self.__class__.Icon = main_Gear_Icon

            # List of gear creation commands
            # Generic gears replace old implementations
            gear_items = [
                # Unified gears (spur, helix, herringbone, cycloidal)
                "GearCommand",
                "InternalGearCommand",
                # Systems
                "PlanetaryGearCreatorCommand",
                "CycloidalGearBoxCreatorCommand",
                # Other gear types
                "RackGearCreateObject",
                "BevelGearCreateObject",
                "CrownGearCreateObject",
                "WormGearCreateObject",
                "GloboidWormGearCommand",
                "HypoidGearCreateObject",
                "ScrewGearCreateObject",
                "NonCircularGearCreateObject",
                "GenevaWheelCreateObject",
                # Tools
                "GearPositioningCommand",
                "GearStackCommand",
                "GearAxlesCommand",
            ]

            # Verify command is available
            import FreeCADGui

            all_commands = FreeCADGui.listCommands()
            for cmd in gear_items:
                if cmd not in all_commands:
                    Err(f"✗ WARNING: Command '{cmd}' NOT found in FreeCAD!\n")
                    Err(f"  Available commands: {len(all_commands)} total\n")

            # Add toolbar and menu
            self.appendToolbar("GearWorkBench", gear_items)
            self.appendMenu("GearWorkBench", gear_items)
            Log("Loading GearWorkBench ... done\n")
            # Msg(f"GearWorkBench toolbar and menu created with commands: {gear_items}\n")
        except Exception as e:
            import traceback

            Err(f"Error initializing GearWorkBench: {e}\n")
            Err(traceback.format_exc())

    def GetClassName(self):
        return "Gui::PythonWorkbench"

    def Activated(self):
        pass  # Msg("GearWorkBench.Activated()\n")

    def Deactivated(self):
        """This function is executed when the workbench is deactivated"""
        pass  # Msg("GearWorkBench.Deactivated()\n")


if not hasattr(FreeCADGui, "_GearWorkBenchWB_loaded"):
    FreeCADGui.addWorkbench(GearWorkBenchWB())
    FreeCADGui._GearWorkBenchWB_loaded = True

# File format pref pages are independent and can be loaded at startup
# FreeCAD.__unit_test__ += ["TestSpurGear"]
