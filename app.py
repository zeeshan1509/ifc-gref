from flask import Flask, render_template, request, redirect, url_for, session, make_response, send_from_directory, jsonify # Import the redirect function
from werkzeug.utils import secure_filename
import os
import ifcopenshell
import ifcopenshell.geom
import georeference_ifc
import re
import pyproj
from pyproj import Transformer
import pint
import numpy as np
import math
from scipy.optimize import leastsq
import pandas as pd
import json
from shapely.geometry import Polygon, mapping
import ifcopenshell.util.placement
import subprocess
import time


app = Flask(__name__, static_url_path='/static', static_folder='static')
app.secret_key = '88746898'
app.config['UPLOAD_FOLDER'] = 'uploads'
ALLOWED_EXTENSIONS = {'ifc'}  # Define allowed file extensions as a set

# Function to check if a filename has an allowed extension
def allowed_file(filename):
    return '.' in filename and filename.rsplit('.', 1)[1].lower() in ALLOWED_EXTENSIONS

def georef(ifc_file):
    geo = False
    #check ifc version
    version = ifc_file.schema
    message = f"IFC version: {version}\n"
    # Check the file is georefed or not
    mapconversion = None
    crs = None

    if ifc_file.schema[:4] == 'IFC4':
        project = ifc_file.by_type("IfcProject")[0]
        for c in (m for c in project.RepresentationContexts for m in c.HasCoordinateOperation):
            mapconversion = c
            crs = c.TargetCRS
        if mapconversion is not None:
            message += "IFC file is georeferenced.\n"
            geo = True
    if ifc_file.schema == 'IFC2X3':
        site = ifc_file.by_type("IfcSite")[0]
        psets = ifcopenshell.util.element.get_psets(site)
        if 'ePSet_MapConversion' in psets.keys() and 'ePSet_ProjectedCRS' in psets.keys():
            message += "IFC file is georeferenced.\n"
            geo = True
    return message , geo
        
def infoExt(filename , epsgCode):
    ureg = pint.UnitRegistry()
    ifc_file = fileOpener(filename)
    
    if ifc_file is None:
        errorMessage = "Could not open IFC file. Please check the file exists and is valid."
        return [], errorMessage
    
    #check ifc version
    version = ifc_file.schema
    messages = [('IFC version', version)]
    ifc_site = ifc_file.by_type("IfcSite")


    #Find Longtitude and Latitude
    RLat = ifc_site[0].RefLatitude
    RLon = ifc_site[0].RefLongitude
    RElev = ifc_site[0].RefElevation
    if RLat is not None and RLon is not None:
        x0= (float(RLat[0]) + float(RLat[1])/60 + float(RLat[2]+RLat[3]/1000000)/(60*60))
        y0= (float(RLon[0]) + float(RLon[1])/60 + float(RLon[2]+RLon[3]/1000000)/(60*60))
        session['Refl'] = True
        if hasattr(ifc_file.by_type("IfcSite")[0], "ObjectPlacement") and ifc_file.by_type("IfcSite")[0].ObjectPlacement.is_a("IfcLocalPlacement"):
            local_placement = ifc_file.by_type("IfcSite")[0].ObjectPlacement.RelativePlacement
                # Check if the local placement is an IfcAxis2Placement3D
            if local_placement.is_a("IfcAxis2Placement3D"):
                local_origin = local_placement.Location.Coordinates
                bx,by,bz= local_origin
                messages.append(('IFC Local Origin', local_origin))
            else:
                    errorMessage = "Local placement is not IfcAxis2Placement3D."
                    return messages, errorMessage
        else:
                errorMessage = "IfcSite does not have a local placement."
                return messages, errorMessage
    else:
        session['Refl'] = False
        messages.append(('RefLatitude or RefLongitude', 'Not available'))
    Refl = session.get('Refl')
    crs = None
    if ifc_file.schema[:4] != 'IFC4' and ifc_file.schema != 'IFC2X3':
        errorMessage = "IFC2X3, IFC4, and newer versions are supported.\n"
        return messages, errorMessage

    # Find local origin

                
    # Target CRS unit name
    try: 
        crs = pyproj.CRS.from_epsg(int(epsgCode))
    except:
        errorMessage = "CRS is not available."
        return messages, errorMessage


    crsunit = crs.axis_info[0].unit_name

    if crs.is_projected:
        messages.append(('Target CRS Type', 'Projected'))
        messages.append(('Target CRS EPSG', epsgCode))

    else:
        errorMessage = "CRS is not projected (geographic)."
        return messages, errorMessage
    target_epsg = "EPSG:"+str(epsgCode)
    transformer = Transformer.from_crs("EPSG:4326", target_epsg)
    # IFC length unit name
    ifc_units = ifc_file.by_type("IfcUnitAssignment")[0].Units
    for ifc_unit in ifc_units:
        if ifc_unit.is_a("IfcSIUnit") and ifc_unit.UnitType == "LENGTHUNIT":
            if ifc_unit.Prefix is not None:
                ifcunit = ifc_unit.Prefix + ifc_unit.Name
            else:
                ifcunit = ifc_unit.Name
    try: 
        quantity = unitmapper(ifcunit)
        ifcmeter = quantity.to(ureg.meter).magnitude
    except:
        ifcmeter = None
    # try:
    #     if ifcunit in unit_mapping:
    #         quantity = 1 * unit_mapping[ifcunit]
    #         ifcmeter = quantity.to(ureg.meter).magnitude
    #     else:
    #         ifcmeter = None
    # except:
    #     ifcmeter = None
    try: 
        quantity = unitmapper(crsunit)
        crsmeter = quantity.to(ureg.meter).magnitude
    except:
        crsmeter = None

    # try:
    #     if crsunit in unit_mapping:
    #         quantity = 1 * unit_mapping[crsunit]
    #         crsmeter = quantity.to(ureg.meter).magnitude
    #     else:
    #         crsmeter = None
    # except:
    #     crsmeter = None

    if crsmeter is not None and ifcmeter is not None:
        coeff= ifcmeter/crsmeter
    else:
        errorMessage = "IFC/Map unit error"
        return messages, errorMessage
    if Refl:
        messages.append(("Reference Longitude",y0))
        messages.append(("Reference Latitude",x0))
        messages.append(("Reference Elevation",RElev))

    messages.append(("Target CRS Unit",str.lower(crsunit)))

    session['mapunit'] = str.lower(crsunit)

    if ifcunit:
        unit_name = ifcunit
        messages.append(("IFC Unit",str.lower(unit_name)))
        session['ifcunit'] = str.lower(unit_name)

    else:
        errorMessage = "No length unit found in the IFC file."
        return messages, errorMessage
    messages.append(("Unit Conversion Ratio",coeff))
    errorMessage = ""
    session['coeff'] = coeff
    if Refl:
        x1,y1,z1 = transformer.transform(x0,y0,RElev)
        x2= x1*coeff
        y2= y1*coeff
        session['xt'] = x1
        session['yt'] = y1
        session['zt'] = z1
        session['Longitude'] = y0
        session['Latitude'] = x0

    return messages, errorMessage

def unitmapper(value):
    ureg = pint.UnitRegistry()
    unit_mapping = {
    "METRE": ureg.meter,
    "METER": ureg.meter,
    "CENTIMETRE": ureg.centimeter,
    "CENTIMETER": ureg.centimeter,
    "MILLIMETRE": ureg.millimeter,
    "MILLIMETER": ureg.millimeter,
    "INCH": ureg.inch,
    "FOOT": ureg.foot,
    "YARD": ureg.yard,
    "MILE": ureg.mile,
    "NAUTICAL_MILE": ureg.nautical_mile,
    "metre": ureg.meter,
    "meter": ureg.meter,
    "centimeter": ureg.centimeter,
    "centimetre": ureg.centimeter,
    "millimeter": ureg.millimeter,
    "millimetre": ureg.millimeter,
    "inch": ureg.inch,
    "foot": ureg.foot,
    "yard": ureg.yard,
    "mile": ureg.mile,
    "nautical_mile": ureg.nautical_mile,
    # Add more mappings as needed
    }
    if value in unit_mapping:
            return  1 * unit_mapping[value]
    return

@app.route('/')
def index():
    return render_template('upload.html')

@app.route('/upload', methods=['POST'])
def upload_file():
    if 'file' not in request.files:
        return "No file part"
    file = request.files['file']
    if file.filename == '':
        return "No selected file"
    if file and allowed_file(file.filename):  # Check if the file extension is allowed
        filename = secure_filename(file.filename)
        file.save(os.path.join(app.config['UPLOAD_FOLDER'], filename))
        ifc_file = fileOpener(filename)

        message, geo = georef(ifc_file)
        if geo:
            IfcMapConversion, IfcProjectedCRS = georeference_ifc.get_mapconversion_crs(ifc_file=ifc_file)
            df = pd.DataFrame(list(IfcProjectedCRS.__dict__.items()), columns= ['property', 'value'])
            dg = pd.DataFrame(list(IfcMapConversion.__dict__.items()), columns= ['property', 'value'])
            html_table_f = df.to_html()
            html_table_g = dg.to_html()
            IfcMapConversion, IfcProjectedCRS = georeference_ifc.get_mapconversion_crs(ifc_file=ifc_file)
            target = IfcProjectedCRS.Name.split(':')
            epsg = int(target[1])
            message2 = infoExt(filename,epsg)
            coeff = session.get('coeff')
            if coeff is None:
                return render_template('result.html', filename=filename, table_f=html_table_f, table_g=html_table_g, message=message2)

            if int(coeff)!=1 and IfcMapConversion.Scale is None:
                message += "There is a conflict between Scale factor and unit conversion. (Yet to be decided by buildingSmart.)"
                session['scaleError']=True
                return render_template('result.html', filename=filename, table_f=html_table_f, table_g=html_table_g, message=message)
            if int(coeff)!=1 and int(IfcMapConversion.Scale) == 1:
                message += "There is a conflict between Scale factor and unit conversion. (Yet to be decided by buildingSmart.)"
                session['scaleError']=True
            return render_template('result.html', filename=filename, table_f=html_table_f, table_g=html_table_g, message=message)
        
        return redirect(url_for('convert_crs', filename=filename))  # Redirect to EPSG code input page
    else:
        return render_template('upload.html', error_message="Invalid file format. Please upload a .ifc file.")

@app.route('/devs', methods=['GET', 'POST'])
def devs_upload():
    if request.method == 'POST':
        if 'file' not in request.files:
            return "No file part"

        file = request.files['file']

        if file.filename == '':
            return "No selected file"

        if file and allowed_file(file.filename):
            filename = secure_filename(file.filename)
            file.save(os.path.join(app.config['UPLOAD_FOLDER'], filename))
            ifc_file = fileOpener(filename)

            # Check if the IFC file is georeferenced
            message, geo = georef(ifc_file)

            if geo:
                IfcMapConversion, IfcProjectedCRS = georeference_ifc.get_mapconversion_crs(ifc_file=ifc_file)
                dg = pd.DataFrame(list(IfcMapConversion.__dict__.items()), columns= ['property', 'value'])
                message += "IfcMapconversion:\n\n" + dg.to_string()
                return f"Filename: {filename}\nGeoreferenced: YES\n{message}"
            else:
                message += "For georeferencing the IFC file, please visit the following address in a web browser:\nhttps://ifcgref.bk.tudelft.nl"
                return f"Filename: {filename}\nGeoreferenced: NO\n{message}"
                
@app.route('/convert/<filename>', methods=['GET', 'POST'])
def convert_crs(filename):
    if request.method == 'POST':
        try:
            epsg_code = int(request.form['epsg_code'])
        except ValueError:
            message = "Invalid EPSG code. Please enter a valid integer."
            return render_template('convert.html', filename=filename, message=message)
        session['target_epsg'] = epsg_code
       # Call the infoExt function and unpack the results
        messages, error = infoExt(filename, epsg_code)
        if error == "":
            # Pass x2, y2, and z1 to the survey_points route
            return redirect(url_for('survey_points', filename=filename))
        return render_template('convert.html', filename=filename, message=error)

    return render_template('convert.html', filename=filename)

@app.route('/survey/<filename>', methods=['GET', 'POST'])
def survey_points(filename):
    epsg_code = session.get('target_epsg')
    
    # Check if we have auto points from interactive georeferencing
    auto_points = session.get('auto_points')
    if auto_points and auto_points.get('filename') == filename:
        # Auto-populate with interactive points
        session['target_epsg'] = auto_points.get('epsg_code', 'EPSG:32643')
        session['rows'] = len(auto_points.get('building_points', []))
        epsg_code = session.get('target_epsg')
        
        # Store the points for form population
        session['auto_building_points'] = auto_points.get('building_points', [])
        session['auto_map_points'] = auto_points.get('map_points', [])
        
        # Clear auto_points to avoid reprocessing
        session.pop('auto_points', None)
    
    messages, error = infoExt(filename, epsg_code)
    ifcunit = session.get('ifcunit')
    mapunit = session.get('mapunit')
    Refl = session.get('Refl')
    if request.method == 'POST':
        box_number = request.form.get('boxNumber')
        if box_number == '3':
            session['Refl'] = False
            Refl = False
    if Refl:
        messages , error = local_trans(filename,messages)
        Num = []
        if request.method == 'POST':
            try:
                Num = int(request.form['Num'])
                if Num < 0:
                    error += "Please enter zero or a positive integer."
                    return render_template('survey.html', filename=filename, messages=messages, error=error)
            except ValueError:
                error += "Please enter zero or a positive integer."
                return render_template('survey.html', filename=filename, messages=messages, error=error)
            session['rows'] = Num
            if Num == 0:
                return redirect(url_for('calculate', filename=filename))
        return render_template('survey.html', filename=filename, messages=messages, Num=Num, ifcunit=ifcunit, mapunit=mapunit, error=error, Refl = Refl)
    else:
        error += '\nThe model has no surveyed or georeferenced attribute.\nYou need to provide at least one point in local and target CRS.'
        error += '\n\nAccuracy of the results improves as you provide more georeferenced points.\nWithout any additional georeferenced points, it is assumed that the model is scaled based on unit conversion and rotation is derived from TrueNorth direction (if availalble).\n'
        Num = []
        if request.method == 'POST':
            try:
                Num = int(request.form['Num'])
                if Num <= 0:
                    error += "Please enter a positive integer."
                    return render_template('survey.html', filename=filename, error=error)
            except ValueError:
                error += "Please enter a positive integer."
                return render_template('survey.html', filename=filename, error=error)
            session['rows'] = Num
        return render_template('survey.html', filename=filename, messages=messages, Num=Num, ifcunit=ifcunit, mapunit=mapunit, Refl = Refl)


def local_trans(filename , messages):
    ifc_file = fileOpener(filename)
    xt = session.get('xt')
    yt = session.get('yt')
    zt = session.get('zt')
    bx,by,bz = 0,0,0
    error = ""
    if hasattr(ifc_file.by_type("IfcSite")[0], "ObjectPlacement") and ifc_file.by_type("IfcSite")[0].ObjectPlacement.is_a("IfcLocalPlacement"):
        local_placement = ifc_file.by_type("IfcSite")[0].ObjectPlacement.RelativePlacement
        # Check if the local placement is an IfcAxis2Placement3D
        if local_placement.is_a("IfcAxis2Placement3D"):
            local_origin = local_placement.Location.Coordinates
            bx, by, bz = map(float, local_origin)
            messages.append(("First Point Local Coordinates",str(local_origin)))
        else:
                error += "Local placement is not IfcAxis2Placement3D."
    else:
            error += "IfcSite does not have a local placement."
    session['bx'] = bx
    session['by'] = by        
    session['bz'] = bz        

    messages.append(("First Point Target coordinates" , ("(" + str(xt) + ", " + str(yt) + ", " + str(zt) + ")")))
    error += '\n\nAccuracy of the results improves as you provide more georeferenced points.\nWithout any additional georeferenced points, it is assumed that the model is scaled based on unit conversion and rotation is derived from TrueNorth direction (if available).\n'

    ifc_file = ifc_file.end_transaction()
    return messages, error

@app.route('/calc/<filename>', methods=['GET', 'POST'])
def calculate(filename):
    #if request.method == 'POST':
        # Access the form data by iterating through the rows
        coeff = session.get('coeff')
        rows = session.get('rows')
        fn = os.path.join(app.config['UPLOAD_FOLDER'], filename)
        ifc_file = fileOpener(filename)
        
        if ifc_file is None:
            return "Error: Could not open IFC file. Please check the file exists and is valid.", 400
        
        data_points = []
        Refl = session.get('Refl')
        if Refl:
            xt = session.get('xt')
            yt = session.get('yt')
            zt = session.get('zt')
            bx = session.get('bx')
            by = session.get('by')
            bz = session.get('bz')
            data_points.append({"X": bx, "Y": by, "Z": bz, "X_prime": xt, "Y_prime": yt, "Z_prime":zt})
        #seperater
        if not Refl and rows == 1:
            Rotation_solution = 0
            # Use reciprocal of coeff for proper IFC transformation
            S_solution = 1.0/coeff  # This correctly scales from IFC mm to CRS meters
            ro = ifc_file.by_type("IfcGeometricRepresentationContext")[0].TrueNorth
            if ro is not None and ro.is_a("IfcDirection"):
                xord , xabs = round(float(ro[0][0]),6) , round(float(ro[0][1]),6)
            else:
                xord , xabs = 0 , 1
            Rotation_solution = math.atan2(xord,xabs)
            A = math.cos(Rotation_solution)
            B = math.sin(Rotation_solution)
            # Fix coordinate transformation - use correct transformation formula
            E_solution = float(request.form[f'x_prime{0}']) - (A*float(request.form[f'x{0}'])*S_solution) + (B*float(request.form[f'y{0}'])*S_solution)
            N_solution = float(request.form[f'y_prime{0}']) - (B*float(request.form[f'x{0}'])*S_solution) - (A*float(request.form[f'y{0}'])*S_solution)
            session['zt'] = float(request.form[f'z_prime{0}'])
            session['bz'] = float(request.form[f'z{0}'])
            H_solution = float(request.form[f'z_prime{0}']) - (float(request.form[f'z{0}'])*S_solution)

        #seperater
        else:
            if rows == 0:
                Rotation_solution = 0
                # Use reciprocal of coeff for proper IFC transformation
                S_solution = 1.0/coeff  # This correctly scales from IFC mm to CRS meters
                ro = ifc_file.by_type("IfcGeometricRepresentationContext")[0].TrueNorth
                if ro is not None and ro.is_a("IfcDirection"):
                    xord , xabs = round(float(ro[0][0]),6) , round(float(ro[0][1]),6)
                else:
                    xord , xabs = 0 , 1
                Rotation_solution = math.atan2(xord,xabs)
                A = math.cos(Rotation_solution)
                B = math.sin(Rotation_solution)
                # Fix coordinate transformation - use correct transformation formula
                E_solution = xt - (A*S_solution*bx) + (B*S_solution*by)
                N_solution = yt - (B*S_solution*bx) - (A*S_solution*by)
                H_solution = zt - (S_solution*bz)
            else:
                for row in range(rows):
                    x = request.form[f'x{row}']
                    y = request.form[f'y{row}']
                    z = request.form[f'z{row}']
                    x_prime = request.form[f'x_prime{row}']
                    y_prime = request.form[f'y_prime{row}']
                    z_prime = request.form[f'z_prime{row}']

                    try:
                        x = float(x)
                        y = float(y)
                        z = float(z)
                        x_prime = float(x_prime)
                        y_prime = float(y_prime)
                        z_prime = float(z_prime)
                    except ValueError:
                        message = "Invalid input. Please enter only float values."
                        Num = rows
                        return render_template('survey.html', message=message, Num=Num)

                    data_points.append({"X": x, "Y": y, "Z":z,"X_prime": x_prime, "Y_prime": y_prime, "Z_prime": z_prime})

                def equations(variables, data_points):
                        S, Rotation, E, N , H = variables
                        eqs = []

                        for data in data_points:
                            X = data["X"]
                            Y = data["Y"]
                            Z = data["Z"]
                            X_prime = data["X_prime"]
                            Y_prime = data["Y_prime"]
                            Z_prime = data["Z_prime"]

                            eq1 = S * np.cos(Rotation) * X - S * np.sin(Rotation) * Y + E - X_prime
                            eq2 = S * np.sin(Rotation) * X + S * np.cos(Rotation) * Y + N - Y_prime
                            eq3 = S*Z + H - Z_prime
                            eqs.extend([eq1, eq2, eq3])

                        return eqs
                    # Initial guess for variables [S, Rotation, E, N]
                if Refl:
                    initial_guess = [coeff, 0, xt, yt, zt]
                else:
                    xg =float(request.form[f'x_prime{0}']) - (float(request.form[f'x{0}'])*coeff)
                    yg = float(request.form[f'y_prime{0}']) - (float(request.form[f'y{0}'])*coeff)
                    zg = float(request.form[f'z_prime{0}']) - (float(request.form[f'z{0}'])*coeff)
                    initial_guess = [coeff,0,xg,yg,zg]

                # Perform the least squares optimization for all data points
                result = leastsq(equations, initial_guess, args=(data_points,), full_output=True)
                S_solution, Rotation_solution, E_solution, N_solution, H_solution = result[0]

        Rotation_degrees = (180 / math.pi) * Rotation_solution
        rDeg = Rotation_degrees - (360*round(Rotation_degrees/360))

        target_epsg = "EPSG:"+str(session.get('target_epsg'))
        georeference_ifc.set_mapconversion_crs(ifc_file=ifc_file,
                                        target_crs_epsg_code=target_epsg,
                                        eastings=E_solution,
                                        northings=N_solution,
                                        orthogonal_height=H_solution,
                                        x_axis_abscissa=math.cos(Rotation_solution),
                                        x_axis_ordinate=math.sin(Rotation_solution),
                                        scale=S_solution)
        fn_output = re.sub('\.ifc$','_georeferenced.ifc', fn)
        ifc_file.write(fn_output)
        IfcMapConversion, IfcProjectedCRS = georeference_ifc.get_mapconversion_crs(ifc_file=ifc_file)
        df = pd.DataFrame(list(IfcProjectedCRS.__dict__.items()), columns= ['property', 'value'])
        dg = pd.DataFrame(list(IfcMapConversion.__dict__.items()), columns= ['property', 'value'])
        dg['value'] = dg['value'].astype(str)
        html_table_f = df.to_html()
        html_table_g = dg.to_html()
        return render_template('result.html', filename=filename, table_f=html_table_f, table_g=html_table_g)
    
def fileOpener(filename):
    fn = os.path.join(app.config['UPLOAD_FOLDER'], filename)
    print("Opening IFC file:", fn)  # Add this line for debugging
    try:
        if not os.path.exists(fn):
            print(f"File does not exist: {fn}")
            return None
        ifc_file = ifcopenshell.open(fn)
        if ifc_file is None:
            print("Failed to open IFC file")
            return None
        return ifc_file
    except Exception as e:
        print("Error opening IFC file:", str(e))  # Add this line for debugging
        return None

@app.route('/show/<filename>', methods=['POST'])
def visualize(filename):
    fn = os.path.join(app.config['UPLOAD_FOLDER'], filename)
    fn_output = re.sub('\.ifc$','_georeferenced.ifc', fn)
    if not os.path.exists(fn_output):
        fn_output = fn
    ifc_file = ifcopenshell.open(fn_output)
    IfcMapConversion, IfcProjectedCRS = georeference_ifc.get_mapconversion_crs(ifc_file=ifc_file)
    target = IfcProjectedCRS.Name.split(':')
    org = ifc_file.by_type('IfcProject')[0].RepresentationContexts[0].WorldCoordinateSystem.Location.Coordinates
    E = IfcMapConversion.Eastings
    N = IfcMapConversion.Northings
    S = IfcMapConversion.Scale
    if S is None:
        S = 1
    ortz = IfcMapConversion.OrthogonalHeight
    cos = IfcMapConversion.XAxisAbscissa
    if cos is None:
        cos = 1    
    sin = IfcMapConversion.XAxisOrdinate
    if sin is None:
        sin = 0
    Rotation_solution = math.atan2(sin,cos)
    A = math.cos(Rotation_solution)
    B = math.sin(Rotation_solution)        
    target_epsg = "EPSG:"+ target[1]
    transformer2 = Transformer.from_crs(target_epsg,"EPSG:4326")
    scaleError = session.get('scaleError')
    Gx , Gy = 0 , 0
    eff = session.get('coeff')
    if scaleError:
        saver = S
        S = eff
        session.pop('scaleError', None)  # Corrected line
        E=E*S
        N = N*S
        ortz= ortz*S
        xx = S * org[0]* A - S * org[1]*B + E
        yy = S * org[1]* A + S * org[1]*B + N
        z = S * org[2] + ortz
        S = saver
        Snew = S
    else:
        xx = S * org[0]* A - S * org[1]*B + E
        yy = S * org[1]* A + S * org[1]*B + N
        zz = S * org[2] + ortz
        Snew = S/eff
    if xx==0 and yy==0:
        products = ifc_file.by_type('IfcProduct')
        for product in products:
            if product.Representation:
                placement = product.ObjectPlacement
                lpMAat = ifcopenshell.util.placement.get_local_placement(placement)
                Gx , Gy = lpMAat[0][3]*eff,lpMAat[1][3]*eff
                xx = xx+Gx
                yy = yy+Gy
                break
    x2,y2 = transformer2.transform(xx,yy)
    Latitude =x2
    Longitude =y2
    projstring = pyproj.CRS(target_epsg).to_proj4()
    crs = pyproj.CRS(projstring)
    alpha_value = crs.to_dict().get('alpha', None)
    Scale_value = crs.to_dict().get('k', None)
    if Scale_value is None:
        Scale_value = 1
    # if Scale_value is not None:
    #     Snew = Snew/Scale_value
    # if alpha_value is not None:
    transformer3 = Transformer.from_crs(target_epsg, "EPSG:3857", always_xy=True)
    x_3857, y_3857 = transformer3.transform(xx, yy)
    xn_3857, yn_3857 = transformer3.transform(xx+1000, yy)
    dx = -x_3857 + xn_3857
    dy = -y_3857 + yn_3857
    angle_radians = math.atan2(dy, dx)
    angle_degrees = math.degrees(angle_radians)
    Rotation_solution = Rotation_solution + angle_radians
    length = math.sqrt(dx**2 + dy**2)
    # transformer3 = Transformer.from_crs(target_epsg, "EPSG:3857", always_xy=True)
    x_3857, y_3857 = transformer3.transform(xx, yy)
    xn_3857, yn_3857 = transformer3.transform((xx+50), (yy+50))
    dx = -x_3857 + xn_3857
    dy = -y_3857 + yn_3857
    length = math.sqrt(dx**2 + dy**2)
    min_z_value = float('inf')

    for product in ifc_file.by_type('IfcProduct'):
    # Check if the product has a placement
        if product.Representation:
            placement = product.ObjectPlacement
            location = ifcopenshell.util.placement.get_local_placement(placement)
            z_value = location[2][3]*eff  # Z is usually the 3rd coordinate (0: X, 1: Y, 2: Z)            
            if z_value < min_z_value:
                min_z_value = z_value
    return render_template('view3D.html', filename=filename, Latitude=Latitude, Longitude=Longitude, Rotate=Rotation_solution, origin = org, Scale = Snew, ScaleCRS = Scale_value, Gx=Gx, Gy=Gy, LowestLevel = min_z_value)

@app.route('/download/<filename>', methods=['GET'])
def download(filename):
    # Define the path to the GeoJSON file
    fn = re.sub('\.ifc$','_georeferenced.ifc', filename)
    file_path = os.path.join(app.config['UPLOAD_FOLDER'], fn)

    # Ensure the file exists
    if os.path.exists(file_path):
        # Set the response headers to indicate a file download
        response = make_response()
        response.headers['Content-Type'] = 'application/octet-stream'
        response.headers['Content-Disposition'] = f'attachment; filename={fn}'
        
        # Read the file content and add it to the response
        with open(file_path, 'rb') as file:
            response.data = file.read()
        
        return response
    else:
        # Return a 404 error if the file doesn't exist
        return 'File not found', 404
@app.route('/templates/<path:filename>')
def temp(filename):
    return send_from_directory('templates', filename)
   
@app.route('/uploads/<path:filename>')
def ups(filename):
    return send_from_directory('uploads', filename)

@app.route('/chek',  methods=['GET', 'POST'])
def chs():
    return render_template('chek.html')

@app.route('/interactive')
def interactive_georef():
    """Interactive georeferencing tool"""
    return render_template('interactive_georef.html')

@app.route('/auto_georeference', methods=['POST'])
def auto_georeference():
    """Auto georeference endpoint that directly processes and redirects to result"""
    try:
        data = request.json
        filename = data.get('filename')
        building_points = data.get('buildingPoints', [])
        map_points = data.get('mapPoints', [])
        epsg_code = data.get('epsgCode', 'EPSG:32643')  # Default to EPSG:32643 for Islamabad
        
        # Store everything in session
        session['target_epsg'] = int(epsg_code.replace('EPSG:', ''))
        session['rows'] = len(building_points)
        session['auto_building_points'] = building_points
        session['auto_map_points'] = map_points
        session['filename'] = filename
        session['auto_mode'] = True
        
        # Also store coordinate data for direct processing
        for i, (building_point, map_point) in enumerate(zip(building_points, map_points)):
            session[f'x{i}'] = building_point['building']['x']
            session[f'y{i}'] = building_point['building']['y'] 
            session[f'z{i}'] = building_point['building']['z']
            session[f'x_prime{i}'] = map_point['coordinates']['easting']
            session[f'y_prime{i}'] = map_point['coordinates']['northing']
            session[f'z_prime{i}'] = map_point['coordinates']['elevation']
        
        return jsonify({
            'success': True,
            'redirect_url': f'/direct_georeference/{filename}'
        })
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)})

@app.route('/direct_georeference/<filename>')
def direct_georeference(filename):
    """Direct route that skips all forms and goes straight to processing"""
    try:
        # Check if we have auto data
        if not session.get('auto_mode'):
            return redirect(url_for('upload'))
        
        # Get data from session
        building_points = session.get('auto_building_points', [])
        map_points = session.get('auto_map_points', [])
        rows = session.get('rows', 0)
        
        if rows == 0:
            return "No points to process", 400
            
        # Render the coordinate input form pre-filled
        return render_template('survey.html', 
                             filename=filename, 
                             Num=rows,
                             auto_mode=True,
                             building_points=building_points,
                             map_points=map_points,
                             messages=[('Auto Georeferencing', f'Processing {rows} points automatically')],
                             ifcunit='MILLIMETRE',
                             mapunit='METRE',
                             Refl=False)
    except Exception as e:
        return f"Error: {str(e)}", 500

@app.route('/test-auto')
def test_auto_georef():
    """Test page for automatic georeferencing workflow"""
    return render_template('test_auto_georef.html')

@app.route('/simple-test')
def simple_test():
    """Simple test page for auto-georeferencing"""
    return render_template('simple_test.html')

@app.route('/api/ifc-analysis/<filename>')
def analyze_ifc_api(filename):
    """API endpoint to analyze IFC file and return coordinate information"""
    try:
        fn = os.path.join(app.config['UPLOAD_FOLDER'], filename)
        if not os.path.exists(fn):
            return {'error': 'File not found'}, 404
        
        ifc_file = ifcopenshell.open(fn)
        
        # Get basic model info
        schema = ifc_file.schema
        products = ifc_file.by_type('IfcProduct')
        
        # Extract coordinates from all products
        coordinates = []
        for product in products:
            if product.Representation and product.ObjectPlacement:
                try:
                    matrix = ifcopenshell.util.placement.get_local_placement(product.ObjectPlacement)
                    x, y, z = matrix[0][3], matrix[1][3], matrix[2][3]
                    coordinates.append([float(x), float(y), float(z)])
                except:
                    continue
        
        if coordinates:
            import numpy as np
            coords_array = np.array(coordinates)
            min_coords = np.min(coords_array, axis=0).tolist()
            max_coords = np.max(coords_array, axis=0).tolist()
            center_coords = np.mean(coords_array, axis=0).tolist()
            dimensions = (coords_array.max(axis=0) - coords_array.min(axis=0)).tolist()
        else:
            min_coords = max_coords = center_coords = dimensions = [0, 0, 0]
        
        return {
            'filename': filename,
            'schema': schema,
            'product_count': len(products),
            'coordinates_count': len(coordinates),
            'bounds': {
                'min': min_coords,
                'max': max_coords,
                'center': center_coords,
                'dimensions': dimensions
            },
            'coordinates': coordinates[:100] if len(coordinates) > 100 else coordinates  # Limit for performance
        }
        
    except Exception as e:
        return {'error': str(e)}, 500

if __name__ == '__main__':
    app.run(debug=True, port=5002)
