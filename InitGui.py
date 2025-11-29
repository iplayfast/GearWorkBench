#***************************************************************************
#*                                                                         *
#*   Copyright (c) 2025                                                    *
#*   Chris Bruner                                                          *
#*                                                                         *
#*   This program is free software; you can redistribute it and/or modify  *
#*   it under the terms of the GNU Lesser General Public License (LGPL)    *
#*   as published by the Free Software Foundation; either version 2 of     *
#*   the License, or (at your option) any later version.                   *
#*   for detail see the LICENCE text file.                                 *
#*                                                                         *
#*   This program is distributed in the hope that it will be useful,       *
#*   but WITHOUT ANY WARRANTY; without even the implied warranty of        *
#*   MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the         *
#*   GNU Library General Public License for more details.                  *
#*                                                                         *
#*   You should have received a copy of the GNU Library General Public     *
#*   License along with this program; if not, write to the Free Software   *
#*   Foundation, Inc., 59 Temple Place, Suite 330, Boston, MA  02111-1307  *
#*   USA                                                                   *
#*                                                                         *
#***************************************************************************

import os
import gearMath
import spurGear  # Import at module level to ensure command registration
import internalGear  # Import internal gear module

smWBpath = os.path.dirname(gearMath.__file__)
smWB_icons_path = os.path.join(smWBpath, 'icons')
global main_Gear_Icon
main_Gear_Icon = os.path.join(smWB_icons_path, 'gearWorkbench.svg')


class GearWorkbenchWB(Workbench):
    """Gear Design Workbench - Parametric gears for 3D printing"""

    MenuText = "GearWorkbench"
    ToolTip = "Parametric gear designer for 3D printing (spur, helical, rack, bevel, etc.)"
    Icon = main_Gear_Icon

    def Initialize(self):
        """This function is executed when FreeCAD starts"""
        try:
            self.__class__.Icon = main_Gear_Icon

            # List of gear creation commands
            gear_items = ["SpurGearCreateObject", "InternalGearCreateObject"]

            # Verify command is available
            import FreeCADGui
            all_commands = FreeCADGui.listCommands()
            for cmd in gear_items:
                if cmd in all_commands:
                    Msg(f"✓ Command '{cmd}' found in FreeCAD\n")
                else:
                    Err(f"✗ WARNING: Command '{cmd}' NOT found in FreeCAD!\n")
                    Err(f"  Available commands: {len(all_commands)} total\n")

            # Add toolbar and menu
            self.appendToolbar("GearWorkbench", gear_items)
            self.appendMenu("GearWorkbench", gear_items)
            Log("Loading GearWorkbench ... done\n")
            Msg(f"GearWorkbench toolbar and menu created with commands: {gear_items}\n")
        except Exception as e:
            import traceback
            Err(f"Error initializing GearWorkbench: {e}\n")
            Err(traceback.format_exc())

    def GetClassName(self):
        return "Gui::PythonWorkbench"

    def Activated(self):
        Msg("GearWorkbench.Activated()\n")

    def Deactivated(self):
        """This function is executed when the workbench is deactivated"""
        Msg("GearWorkbench.Deactivated()\n")


FreeCADGui.addWorkbench(GearWorkbenchWB())

# File format pref pages are independent and can be loaded at startup
# FreeCAD.__unit_test__ += ["TestSpurGear"]
