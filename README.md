
# IfcGref Web-Based Application

![ifcgref-release](https://github.com/tudelft3d/ifcgref/assets/50393714/e335cd23-d063-4f86-8cdf-d9898b6a955a)


## Overview

This Flask-based application serves the purpose of georeferencing IFC (Industry Foundation Classes) files, which are commonly used in the context of Building Information Modeling (BIM) data exchange. To accomplish georeferencing, the application leverages the **IFCMapConversion** entity in IFC4, which facilitates the updating of data and the conversion from a local Coordinate Reference System (CRS), often referred to as the engineering coordinate system, into the coordinate reference system of the underlying map (Projected CRS). It's accessible at https://ifcgref.bk.tudelft.nl.



## Prerequisites

Before running the application, make sure you have the following prerequisites installed on your system:

- Python 3
- Flask
- ifcopenshell
- pyproj
- pint
- numpy
- scipy
- pandas
- shapely

You can install these dependencies using pip:

```bash
pip install -r requirements.txt
```

Or install individually:

```bash
pip install Flask ifcopenshell pyproj pint numpy scipy pandas shapely
```

## Supported IFC versions


Coordinate operations become accessible starting from IFC 4. For earlier versions like the widely utilized IFC2x3, the utilization of Property sets (Pset) is employed to enable georeferencing. The table below outlines the supported versions: 

| Version | Name |
| -------- | ------- |
| 4.3.2.0 | IFC 4.3 ADD2 |
| 4.0.2.0 | IFC4 ADD2 TC1 |
| 4.0.2.1 | IFC4 ADD2 |
| 4.0.2.0	| IFC4 ADD1 |
| 4.0.0.0 | IFC4 |
| 2.3.0.1 | IFC2x3 TC1 |
| 2.3.0.0 | IFC2x3 |


## Usage

### Method 1: Interactive Georeferencing

The application now features an interactive interface that allows you to visually select correspondence points between your IFC building model and real-world map locations.

#### Step 1: Start the Application
1. Clone this repository or download the application files to your local machine.
2. Navigate to the project directory in your terminal.
3. Run the Flask application:

```bash
python app.py
```

4. Access the application in your web browser by going to http://localhost:5003/.

#### Step 2: Upload Your IFC File
- Click "Interactive Georeferencing" on the homepage
- Upload your IFC file (you can use the sample file `Ifc4_SampleHouse_0_GroundFloor.ifc` located in the root directory)
- The system will analyze the file and display a 3D visualization of your building

#### Step 3: Select Correspondence Points
- **Building Model View (Left Side)**: Click on specific points within your 3D building model to select reference points
  - Choose corners, edges, or distinctive features of your building
  - The system displays your building as a rectangle with red corner markers and green edge markers
  - Select at least 1 point (more points improve accuracy)
  - **After selecting points on the building, click the "Next" button to proceed to the map view**

- **Map View (Right Side)**: After clicking "Next", you'll see the interactive map
  - Navigate to your target location 
  - Click on the exact map location that corresponds to each building point you selected
  - The system automatically detects the appropriate coordinate system (e.g., EPSG:32643 for Islamabad)
  - Ensure you select the same number of points on the map as you did on the building

#### Step 4: Process Georeferencing
- Once you've selected corresponding points on both the building and map, click "Submit Points"
- The system will automatically:
  - Calculate coordinate transformations
  - Apply proper scale factors (converts IFC millimeters to real-world meters)
  - Handle coordinate system conversions (lat/lon to UTM)
  - Perform rotation and translation calculations

#### Step 5: Download Results
- Review the transformation results and coordinate details
- Download the georeferenced IFC file with "_georeferenced.ifc" suffix
- The file is now properly positioned in real-world coordinates

### Method 2: Traditional Manual Input

1. Follow steps 1-4 from Method 1 to start the application
2. Choose "Manual Georeferencing" instead of interactive mode
3. Follow the on-screen instructions to upload an IFC file and specify the target EPSG code
4. Manually enter coordinate values for georeferencing points
5. The application will georeference the IFC file and provide details about the process
6. You can then visualize the georeferenced IFC file on the map and download it

### Example Usage with Sample File

To test the interactive georeferencing:

1. Start the application as described above
2. Select "Interactive Georeferencing"
3. Upload the provided sample file: `Ifc4_SampleHouse_0_GroundFloor.ifc`
4. In the building view, click on a corner of the displayed house model
5. In the map view, navigate to Islamabad, Pakistan and click on a location where you want to place the building
6. Click "Submit Points" to process the georeferencing
7. Download the resulting georeferenced IFC file

## File Structure

- `app.py`: The main Flask application file
- `Ifc4_SampleHouse_0_GroundFloor.ifc`: Sample IFC file for testing the interactive georeferencing
- `requirements.txt`: Python package dependencies
- `static/`: Directory to store static files (CSS, images, JavaScript)
- `templates/`: HTML templates for the web interface including interactive georeferencing
- `uploads/`: Directory to temporarily store uploaded IFC files
- `georeference_ifc/`: Core georeferencing module

## Workflow

![Screenshot 2024-02-26 at 17 28 20 (2)](https://github.com/tudelft3d/ifcgref/assets/50393714/3d14b4c7-9652-4b77-bc5b-77bd2a736341)
