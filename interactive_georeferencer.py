#!/usr/bin/env python3
"""
Interactive IFC Georeferencing Tool
Allows visual selection of points on IFC model and mapping to geographic coordinates
"""
import ifcopenshell
import ifcopenshell.util.placement
import ifcopenshell.geom
import numpy as np
import sys
import os
import matplotlib.pyplot as plt
from mpl_toolkits.mplot3d import Axes3D
import matplotlib.patches as patches
from matplotlib.widgets import Button
import pyproj
import json

class InteractiveGeoreferencer:
    def __init__(self, ifc_file_path):
        self.ifc_file_path = ifc_file_path
        self.ifc_file = ifcopenshell.open(ifc_file_path)
        self.selected_points = []
        self.target_points = []
        self.current_mode = 'building'  # 'building' or 'map'
        self.fig = None
        self.ax = None
        self.building_elements = []
        self.epsg_code = 'EPSG:32643'  # Default to Islamabad UTM
        
        # Initialize coordinate transformer
        self.transformer_to_wgs84 = pyproj.Transformer.from_crs(self.epsg_code, 'EPSG:4326', always_xy=True)
        
        # Analyze the IFC model
        self.analyze_model()
        
    def analyze_model(self):
        """Analyze the IFC model to extract geometry and coordinates"""
        print(f"Analyzing IFC model: {os.path.basename(self.ifc_file_path)}")
        
        # Create geometry settings
        settings = ifcopenshell.geom.settings()
        settings.set(settings.USE_WORLD_COORDS, True)
        
        # Extract all building elements with their positions
        products = self.ifc_file.by_type('IfcProduct')
        
        for product in products:
            if product.Representation and product.ObjectPlacement:
                try:
                    # Get the placement matrix
                    matrix = ifcopenshell.util.placement.get_local_placement(product.ObjectPlacement)
                    x, y, z = matrix[0][3], matrix[1][3], matrix[2][3]
                    
                    # Try to get geometry for visualization
                    try:
                        shape = ifcopenshell.geom.create_shape(settings, product)
                        geometry = shape.geometry
                        vertices = shape.geometry.verts
                        faces = shape.geometry.faces
                        
                        # Convert vertices to numpy array and reshape
                        vertices_array = np.array(vertices).reshape(-1, 3)
                        
                        self.building_elements.append({
                            'type': product.is_a(),
                            'name': getattr(product, 'Name', 'Unnamed'),
                            'global_id': getattr(product, 'GlobalId', 'No ID'),
                            'position': [x, y, z],
                            'vertices': vertices_array,
                            'faces': faces
                        })
                    except:
                        # If geometry creation fails, just store position
                        self.building_elements.append({
                            'type': product.is_a(),
                            'name': getattr(product, 'Name', 'Unnamed'),
                            'global_id': getattr(product, 'GlobalId', 'No ID'),
                            'position': [x, y, z],
                            'vertices': np.array([[x, y, z]]),
                            'faces': []
                        })
                        
                except Exception as e:
                    continue
        
        print(f"Found {len(self.building_elements)} building elements")
        
        # Calculate model bounds
        all_vertices = []
        for element in self.building_elements:
            if len(element['vertices']) > 0:
                all_vertices.extend(element['vertices'])
        
        if all_vertices:
            all_vertices = np.array(all_vertices)
            self.model_bounds = {
                'min': np.min(all_vertices, axis=0),
                'max': np.max(all_vertices, axis=0),
                'center': np.mean(all_vertices, axis=0)
            }
            self.model_size = self.model_bounds['max'] - self.model_bounds['min']
            print(f"Model bounds: {self.model_bounds['min']} to {self.model_bounds['max']}")
            print(f"Model size: {self.model_size}")
        else:
            print("Warning: No geometry found in model")
    
    def show_building_view(self):
        """Show 3D view of the building for point selection"""
        print("\\n=== BUILDING VIEW ===")
        print("Click on points in the building to select control points")
        print("You need to select at least 3 points")
        
        # Create 3D plot
        self.fig = plt.figure(figsize=(12, 8))
        self.ax = self.fig.add_subplot(111, projection='3d')
        
        # Plot building elements
        colors = plt.cm.tab10(np.linspace(0, 1, len(self.building_elements)))
        
        for i, element in enumerate(self.building_elements):
            vertices = element['vertices']
            if len(vertices) > 0:
                # Plot vertices as points
                self.ax.scatter(vertices[:, 0], vertices[:, 1], vertices[:, 2], 
                              c=[colors[i]], s=20, alpha=0.6, 
                              label=f"{element['type'][:10]}...")
        
        # Set axis labels and title
        self.ax.set_xlabel('X (m)')
        self.ax.set_ylabel('Y (m)')
        self.ax.set_zlabel('Z (m)')
        self.ax.set_title('IFC Building Model - Click to Select Points')
        
        # Add legend if not too many elements
        if len(self.building_elements) < 10:
            self.ax.legend(bbox_to_anchor=(1.05, 1), loc='upper left')
        
        # Connect click event
        self.fig.canvas.mpl_connect('button_press_event', self.on_building_click)
        
        # Add buttons
        self.add_control_buttons()
        
        plt.tight_layout()
        plt.show()
    
    def show_map_view(self):
        """Show map view for geographic point selection"""
        print("\\n=== MAP VIEW ===")
        print("Click on the map to set geographic coordinates for each selected building point")
        print(f"Using coordinate system: {self.epsg_code}")
        
        # Create a simple map visualization
        # For now, we'll use a coordinate grid. In a full implementation, 
        # this could be integrated with a web map
        self.fig, self.ax = plt.subplots(figsize=(10, 8))
        
        # Default to Islamabad area
        center_x, center_y = 319050, 3728874  # Islamabad in UTM
        
        # Create a grid showing the area
        x_range = np.linspace(center_x - 500, center_x + 500, 100)
        y_range = np.linspace(center_y - 500, center_y + 500, 100)
        X, Y = np.meshgrid(x_range, y_range)
        
        # Plot the coordinate grid
        self.ax.contour(X, Y, np.zeros_like(X), levels=[0], colors='lightgray', alpha=0.5)
        self.ax.grid(True, alpha=0.3)
        
        # Convert to lat/lon for display
        lon_center, lat_center = self.transformer_to_wgs84.transform(center_x, center_y)
        
        self.ax.set_xlabel(f'Easting ({self.epsg_code}) [m]')
        self.ax.set_ylabel(f'Northing ({self.epsg_code}) [m]')
        self.ax.set_title(f'Geographic Coordinate Selection\\nCenter: {lat_center:.6f}°N, {lon_center:.6f}°E')
        
        # Set equal aspect ratio
        self.ax.set_aspect('equal')
        
        # Show selected building points info
        if self.selected_points:
            info_text = "Selected building points:\\n"
            for i, point in enumerate(self.selected_points):
                info_text += f"P{i+1}: ({point[0]:.2f}, {point[1]:.2f}, {point[2]:.2f})\\n"
            
            self.ax.text(0.02, 0.98, info_text, transform=self.ax.transAxes, 
                        verticalalignment='top', bbox=dict(boxstyle='round', facecolor='wheat', alpha=0.8))
        
        # Connect click event
        self.fig.canvas.mpl_connect('button_press_event', self.on_map_click)
        
        # Add control buttons
        self.add_control_buttons()
        
        plt.tight_layout()
        plt.show()
    
    def on_building_click(self, event):
        """Handle clicks on the building view"""
        if event.inaxes != self.ax:
            return
        
        if event.button == 1:  # Left click
            # Find the closest point to the click
            click_point = np.array([event.xdata, event.ydata, 0])  # Z will be interpolated
            
            # Find closest vertex from all building elements
            closest_distance = float('inf')
            closest_point = None
            
            for element in self.building_elements:
                vertices = element['vertices']
                for vertex in vertices:
                    # Calculate 2D distance (ignore Z for clicking)
                    distance = np.sqrt((vertex[0] - event.xdata)**2 + (vertex[1] - event.ydata)**2)
                    if distance < closest_distance:
                        closest_distance = distance
                        closest_point = vertex
            
            if closest_point is not None:
                self.selected_points.append(closest_point)
                
                # Plot the selected point
                self.ax.scatter([closest_point[0]], [closest_point[1]], [closest_point[2]], 
                              c='red', s=100, marker='o')
                self.ax.text(closest_point[0], closest_point[1], closest_point[2], 
                           f'  P{len(self.selected_points)}', fontsize=12, color='red')
                
                print(f"Selected point {len(self.selected_points)}: ({closest_point[0]:.3f}, {closest_point[1]:.3f}, {closest_point[2]:.3f})")
                
                self.fig.canvas.draw()
                
                # If we have enough points, suggest moving to map view
                if len(self.selected_points) >= 3:
                    print("\\nYou have selected enough points! You can now:")
                    print("1. Click 'Next: Map View' to set geographic coordinates")
                    print("2. Or continue selecting more points for better accuracy")
    
    def on_map_click(self, event):
        """Handle clicks on the map view"""
        if event.inaxes != self.ax:
            return
        
        if event.button == 1:  # Left click
            # Get the coordinates where clicked
            x_coord = event.xdata
            y_coord = event.ydata
            
            # Default elevation (can be adjusted)
            z_coord = 540  # Islamabad elevation
            
            # Add to target points
            target_point = [x_coord, y_coord, z_coord]
            self.target_points.append(target_point)
            
            # Plot the selected point
            self.ax.scatter([x_coord], [y_coord], c='blue', s=100, marker='s')
            self.ax.text(x_coord, y_coord, f'  T{len(self.target_points)}', 
                        fontsize=12, color='blue')
            
            # Convert to lat/lon for display
            lon, lat = self.transformer_to_wgs84.transform(x_coord, y_coord)
            
            print(f"Target point {len(self.target_points)}: ({x_coord:.2f}, {y_coord:.2f}, {z_coord}) = {lat:.6f}°N, {lon:.6f}°E")
            
            self.fig.canvas.draw()
            
            # Check if we have enough points
            if len(self.target_points) >= len(self.selected_points):
                print("\\nAll points mapped! You can now:")
                print("1. Click 'Generate Config' to create the georeferencing configuration")
                print("2. Or continue adjusting points")
    
    def add_control_buttons(self):
        """Add control buttons to the interface"""
        # Create button axes
        button_height = 0.04
        button_width = 0.15
        button_spacing = 0.02
        
        # Next/Map View button
        if self.current_mode == 'building':
            ax_next = plt.axes([0.02, 0.02, button_width, button_height])
            self.btn_next = Button(ax_next, 'Next: Map View')
            self.btn_next.on_clicked(self.switch_to_map_view)
        
        # Generate Config button
        ax_generate = plt.axes([0.02 + button_width + button_spacing, 0.02, button_width, button_height])
        self.btn_generate = Button(ax_generate, 'Generate Config')
        self.btn_generate.on_clicked(self.generate_config)
        
        # Clear Points button
        ax_clear = plt.axes([0.02 + 2*(button_width + button_spacing), 0.02, button_width, button_height])
        self.btn_clear = Button(ax_clear, 'Clear Points')
        self.btn_clear.on_clicked(self.clear_points)
    
    def switch_to_map_view(self, event):
        """Switch from building view to map view"""
        if len(self.selected_points) < 3:
            print("Please select at least 3 points before proceeding to map view")
            return
        
        self.current_mode = 'map'
        plt.close(self.fig)
        self.show_map_view()
    
    def clear_points(self, event):
        """Clear all selected points"""
        if self.current_mode == 'building':
            self.selected_points.clear()
            print("Cleared all selected building points")
        else:
            self.target_points.clear()
            print("Cleared all target geographic points")
        
        # Refresh the view
        plt.close(self.fig)
        if self.current_mode == 'building':
            self.show_building_view()
        else:
            self.show_map_view()
    
    def generate_config(self, event):
        """Generate the georeferencing configuration"""
        if len(self.selected_points) < 3 or len(self.target_points) < 3:
            print("Error: Need at least 3 building points and 3 target points")
            return
        
        if len(self.selected_points) != len(self.target_points):
            print("Error: Number of building points must match number of target points")
            return
        
        print("\\n" + "="*60)
        print("GEOREFERENCING CONFIGURATION")
        print("="*60)
        print(f"EPSG Code: {self.epsg_code}")
        print(f"Number of control points: {len(self.selected_points)}")
        print()
        
        # Generate the configuration for the web application
        print("Use these coordinates in your web application:")
        print()
        print("Local IFC coordinates (meters):")
        for i, point in enumerate(self.selected_points):
            print(f"P{i+1} = ({point[0]:.3f}, {point[1]:.3f}, {point[2]:.3f})")
        
        print()
        print(f"Target coordinates in {self.epsg_code}:")
        for i, point in enumerate(self.target_points):
            lon, lat = self.transformer_to_wgs84.transform(point[0], point[1])
            print(f"P{i+1}' = ({point[0]:.2f}, {point[1]:.2f}, {point[2]:.1f})  [{lat:.6f}°N, {lon:.6f}°E]")
        
        # Save configuration to file
        config = {
            'ifc_file': os.path.basename(self.ifc_file_path),
            'epsg_code': self.epsg_code,
            'building_points': [[float(p[0]), float(p[1]), float(p[2])] for p in self.selected_points],
            'target_points': [[float(p[0]), float(p[1]), float(p[2])] for p in self.target_points],
            'timestamp': str(np.datetime64('now'))
        }
        
        config_filename = f"georef_config_{os.path.splitext(os.path.basename(self.ifc_file_path))[0]}.json"
        with open(config_filename, 'w') as f:
            json.dump(config, f, indent=2)
        
        print(f"\\nConfiguration saved to: {config_filename}")
        print("\\nTo use in the web application:")
        print("1. Upload your IFC file")
        print(f"2. Enter EPSG code: {self.epsg_code.split(':')[1]}")
        print("3. Enter the control points as shown above")
        print("4. Submit to georeference your model")

def main():
    """Main function"""
    print("Interactive IFC Georeferencing Tool")
    print("="*50)
    
    # Get IFC file
    if len(sys.argv) > 1:
        ifc_file_path = sys.argv[1]
        if not ifc_file_path.startswith('/'):
            ifc_file_path = os.path.join('uploads', ifc_file_path)
    else:
        # List available files
        uploads_dir = "uploads"
        if os.path.exists(uploads_dir):
            ifc_files = [f for f in os.listdir(uploads_dir) if f.endswith('.ifc') and not f.endswith('_georeferenced.ifc')]
            
            if not ifc_files:
                print("No IFC files found in uploads directory")
                return
            
            print("Available IFC files:")
            for i, f in enumerate(ifc_files, 1):
                print(f"{i}. {f}")
            
            try:
                choice = int(input(f"\\nSelect file (1-{len(ifc_files)}): ")) - 1
                if 0 <= choice < len(ifc_files):
                    ifc_file_path = os.path.join(uploads_dir, ifc_files[choice])
                else:
                    print("Invalid choice")
                    return
            except (ValueError, KeyboardInterrupt):
                print("Cancelled")
                return
        else:
            print("Uploads directory not found")
            return
    
    if not os.path.exists(ifc_file_path):
        print(f"File not found: {ifc_file_path}")
        return
    
    # Create georeferencer and start interactive session
    georef = InteractiveGeoreferencer(ifc_file_path)
    
    print("\\nStarting interactive georeferencing...")
    print("\\nInstructions:")
    print("1. First, you'll see a 3D view of your building")
    print("2. Click on 3 or more points in the building that you can identify")
    print("3. Then you'll see a map view to set geographic coordinates")
    print("4. Click on corresponding locations on the map")
    print("5. Generate the configuration to use in the web application")
    
    input("\\nPress Enter to start...")
    
    georef.show_building_view()

if __name__ == "__main__":
    main()
