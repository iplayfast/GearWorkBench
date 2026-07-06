"""Lantern Gear generator for FreeCAD (Stub)"""
import FreeCAD as App
import FreeCADGui
import gearMath
import os

smWBpath = os.path.dirname(gearMath.__file__)
smWB_icons_path = os.path.join(smWBpath, 'icons')
global mainIcon
mainIcon = os.path.join(smWB_icons_path, 'lanternGear.svg') 

def QT_TRANSLATE_NOOP(scope, text): return text

class LanternGearCreateObject():
    def GetResources(self):
        return {'Pixmap': mainIcon, 'MenuText': "&Create Lantern Gear", 'ToolTip': "Create parametric lantern gear (Stub)"}

    def Activated(self):
        if not App.ActiveDocument: App.newDocument()
        doc = App.ActiveDocument
        gear_obj = doc.addObject("Part::FeaturePython", "LanternGearParameters")
        gear = LanternGear(gear_obj)
        doc.recompute()
        return gear

    def IsActive(self): return True

class LanternGear():
    def __init__(self, obj):
        obj.addProperty("App::PropertyString", "Version", "read only", QT_TRANSLATE_NOOP("App::Property", "Version"), 1).Version = "Stub"
        obj.Proxy = self

    def execute(self, obj): pass 

class ViewProviderLanternGear:
    def __init__(self, obj, iconfile=None):
        obj.Proxy = self
        self.iconfile = iconfile if iconfile else mainIcon
    def attach(self, obj): self.Object = obj.Object
    def getIcon(self): return self.iconfile
    def __getstate__(self): return self.iconfile
    def __setstate__(self, state): self.iconfile = state if state else mainIcon

try: FreeCADGui.addCommand('LanternGearCreateObject', LanternGearCreateObject())
except Exception: pass