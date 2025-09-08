#!/usr/bin/env python3
"""
Script to analyze IFC file coordinates and help identify control points
"""
import ifcopenshell
import ifcopenshell.util.placement
import numpy as np
import sys
import os

def analyze_ifc_coordinates(ifc_file_path):
    """Analyze an IFC file to understand its coordinate system and find key points"""
    
    if not os.path.exists(ifc_file_path):
        print(f"File not found: {ifc_file_path}")
        return
    
    try:
        ifc_file = ifcopenshell.open(ifc_file_path)
        print(f"Analyzing: {os.path.basename(ifc_file_path)}")
        print(f"IFC Schema: {ifc_file.schema}")
        print("=" * 60)
        
        # Get world coordinate system origin
        try:
            project = ifc_file.by_type('IfcProject')[0]
            world_origin = project.RepresentationContexts[0].WorldCoordinateSystem.Location.Coordinates
            print(f"World Coordinate System Origin: {world_origin}")
        except:
            print("Could not retrieve World Coordinate System Origin")
        
        # Analyze all products with placements
        all_coordinates = []
        products_with_coords = []
        
        products = ifc_file.by_type('IfcProduct')
        print(f"Total products in model: {len(products)}")
        
        for product in products:
            if product.Representation and product.ObjectPlacement:
                try:
                    # Get the local placement matrix
                    matrix = ifcopenshell.util.placement.get_local_placement(product.ObjectPlacement)
                    
                    # Extract translation (position) from the matrix
                    x, y, z = matrix[0][3], matrix[1][3], matrix[2][3]
                    all_coordinates.append([x, y, z])
                    
                    # Store product info with coordinates
                    products_with_coords.append({
                        'type': product.is_a(),
                        'name': getattr(product, 'Name', 'Unnamed'),
                        'global_id': getattr(product, 'GlobalId', 'No ID'),
                        'coordinates': [x, y, z]
                    })
                    
                except Exception as e:
                    continue
        
        if not all_coordinates:
            print("No coordinate data found in the model")
            return
        
        # Convert to numpy array for analysis
        coords_array = np.array(all_coordinates)
        
        # Calculate bounding box
        min_coords = np.min(coords_array, axis=0)
        max_coords = np.max(coords_array, axis=0)
        center_coords = (min_coords + max_coords) / 2
        dimensions = max_coords - min_coords
        
        print(f"\nModel Bounding Box Analysis:")
        print(f"Minimum coordinates: X={min_coords[0]:.3f}, Y={min_coords[1]:.3f}, Z={min_coords[2]:.3f}")
        print(f"Maximum coordinates: X={max_coords[0]:.3f}, Y={max_coords[1]:.3f}, Z={max_coords[2]:.3f}")
        print(f"Center coordinates:  X={center_coords[0]:.3f}, Y={center_coords[1]:.3f}, Z={center_coords[2]:.3f}")
        print(f"Model dimensions:    X={dimensions[0]:.3f}m, Y={dimensions[1]:.3f}m, Z={dimensions[2]:.3f}m")
        
        # Suggest control points - BETTER APPROACH for georeferencing
        print(f"\nSuggested Control Points for Georeferencing:")
        print(f"The model is very large ({dimensions[0]:.1f}m x {dimensions[1]:.1f}m), so we'll use a localized approach.")
        print(f"")
        
        # For large models, use a smaller representative area near the center
        # This prevents the model from appearing too large on the map
        
        if dimensions[0] > 1000 or dimensions[1] > 1000:
            print("RECOMMENDED APPROACH - Using localized coordinates:")
            print("Instead of using the full model extent, use a small representative area:")
            print("")
            
            # Use center point as origin and create 100m grid around it
            center_x, center_y, center_z = center_coords
            
            # Option 1: Localized grid around center
            p1_local = [0, 0, 0]  # Set center as local origin
            p2_local = [100, 0, 0]  # 100m east
            p3_local = [0, 100, 0]  # 100m north
            
            print(f"Option 1 - Use these LOCAL coordinates (recommended):")
            print(f"P1 = ({p1_local[0]}, {p1_local[1]}, {p1_local[2]}) [Local origin]")
            print(f"P2 = ({p2_local[0]}, {p2_local[1]}, {p2_local[2]}) [100m east]")
            print(f"P3 = ({p3_local[0]}, {p3_local[1]}, {p3_local[2]}) [100m north]")
            print(f"")
            print(f"Option 2 - If you must use actual IFC coordinates:")
            
        # Point 1: Use center as reference point for large models
        if dimensions[0] > 1000 or dimensions[1] > 1000:
            p1 = [center_coords[0], center_coords[1], min_coords[2]]
            print(f"P1 (center-based):        ({p1[0]:.3f}, {p1[1]:.3f}, {p1[2]:.3f})")
            
            # Point 2: 100m along X-axis from center
            p2 = [center_coords[0] + 100, center_coords[1], min_coords[2]]
            print(f"P2 (+100m in X):          ({p2[0]:.3f}, {p2[1]:.3f}, {p2[2]:.3f})")
            
            # Point 3: 100m along Y-axis from center  
            p3 = [center_coords[0], center_coords[1] + 100, min_coords[2]]
            print(f"P3 (+100m in Y):          ({p3[0]:.3f}, {p3[1]:.3f}, {p3[2]:.3f})")
        else:
            # For smaller models, use corner-based approach
            p1 = [min_coords[0], min_coords[1], min_coords[2]]
            print(f"P1 (bottom-left corner):  ({p1[0]:.3f}, {p1[1]:.3f}, {p1[2]:.3f})")
            
            # Point 2: Along X-axis
            x_offset = min(100.0, dimensions[0])
            p2 = [min_coords[0] + x_offset, min_coords[1], min_coords[2]]
            print(f"P2 (+{x_offset:.1f}m in X direction): ({p2[0]:.3f}, {p2[1]:.3f}, {p2[2]:.3f})")
            
            # Point 3: Along Y-axis
            y_offset = min(100.0, dimensions[1])
            p3 = [min_coords[0], min_coords[1] + y_offset, min_coords[2]]
            print(f"P3 (+{y_offset:.1f}m in Y direction): ({p3[0]:.3f}, {p3[1]:.3f}, {p3[2]:.3f})")
        
        # Show some specific building elements for reference
        print(f"\nBuilding Elements for Reference:")
        print(f"{'Type':<20} {'Name':<20} {'Coordinates'}")
        print("-" * 70)
        
        # Show first 10 elements as examples
        for i, product in enumerate(products_with_coords[:10]):
            coords = product['coordinates']
            name = product['name'][:18] if product['name'] else 'Unnamed'
            print(f"{product['type']:<20} {name:<20} ({coords[0]:.2f}, {coords[1]:.2f}, {coords[2]:.2f})")
        
        if len(products_with_coords) > 10:
            print(f"... and {len(products_with_coords) - 10} more elements")
        
        return {
            'min_coords': min_coords,
            'max_coords': max_coords,
            'center_coords': center_coords,
            'dimensions': dimensions,
            'suggested_points': [p1, p2, p3]
        }
        
    except Exception as e:
        print(f"Error analyzing IFC file: {e}")
        return None

def main():
    """Main function to run the analysis"""
    
    # Default to analyzing all IFC files in uploads folder
    uploads_dir = "uploads"
    
    if len(sys.argv) > 1:
        # If filename provided as argument
        filename = sys.argv[1]
        if not filename.startswith('/'):
            filepath = os.path.join(uploads_dir, filename)
        else:
            filepath = filename
        analyze_ifc_coordinates(filepath)
    else:
        # Analyze all IFC files in uploads directory
        if os.path.exists(uploads_dir):
            ifc_files = [f for f in os.listdir(uploads_dir) if f.endswith('.ifc') and not f.endswith('_georeferenced.ifc')]
            
            if not ifc_files:
                print("No IFC files found in uploads directory")
                return
            
            print("Available IFC files:")
            for i, f in enumerate(ifc_files, 1):
                print(f"{i}. {f}")
            
            try:
                choice = input(f"\nEnter number (1-{len(ifc_files)}) to analyze, or press Enter to analyze all: ")
                
                if choice.strip():
                    idx = int(choice) - 1
                    if 0 <= idx < len(ifc_files):
                        filepath = os.path.join(uploads_dir, ifc_files[idx])
                        analyze_ifc_coordinates(filepath)
                    else:
                        print("Invalid choice")
                else:
                    # Analyze all files
                    for filename in ifc_files:
                        filepath = os.path.join(uploads_dir, filename)
                        analyze_ifc_coordinates(filepath)
                        print("\n" + "="*80 + "\n")
                        
            except (ValueError, KeyboardInterrupt):
                print("Analysis cancelled")
        else:
            print(f"Directory '{uploads_dir}' not found")

if __name__ == "__main__":
    main()
