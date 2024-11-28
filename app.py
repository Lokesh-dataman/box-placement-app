import math
import logging
from collections import Counter
import streamlit as st
import plotly.graph_objects as go

# ----------------------------- #
#          Classes              #
# ----------------------------- #

class Box:
    def __init__(self, name, length, width, height, weight, box_id):
        self.name = name
        self.original_length = length
        self.original_width = width
        self.original_height = height
        self.weight = weight
        self.box_id = box_id
        self.placed = False
        self.position = None  # (x, y, z) coordinates
        self.length = length
        self.width = width
        self.height = height
        self.support_threshold_used = 80  # Default support threshold used
        # Assign a unique color for visualization
        color_list = [
            'red', 'green', 'blue', 'orange', 'purple',
            'yellow', 'pink', 'cyan', 'magenta', 'lime',
            'teal', 'brown', 'grey', 'olive', 'navy',
            'maroon', 'gold', 'coral', 'turquoise', 'violet'
        ]
        self.color = color_list[box_id % len(color_list)]

    def get_rotations(self):
        """Generate the two unique base rotations of the box, sorted to prioritize better placement."""
        rotations = [
            (self.original_length, self.original_width, self.original_height),
            (self.original_width, self.original_length, self.original_height)
        ]
        # Sort rotations to prioritize smaller length (to fit more boxes side by side)
        rotations.sort(key=lambda r: r[0])  # Sort by length
        return rotations

    def dimension_tuple(self):
        """Return dimensions as a tuple for grouping."""
        return tuple(sorted([self.original_length, self.original_width, self.original_height]))

class Pallet:
    def __init__(self, length, width, height, pallet_id):
        self.length = length
        self.width = width
        self.height = height
        self.pallet_id = pallet_id

# ----------------------------- #
#        Helper Functions       #
# ----------------------------- #

def group_boxes_by_dimensions(boxes):
    """Group boxes by their dimensions and count the quantity."""
    groups = {}
    for box in boxes:
        dims = box.dimension_tuple()
        if dims not in groups:
            groups[dims] = {'boxes': [], 'volume': box.original_length * box.original_width * box.original_height}
        groups[dims]['boxes'].append(box)
    return groups

def sort_boxes_by_group_priority(groups):
    """Sort groups by total volume (volume * quantity) in descending order."""
    sorted_groups = sorted(groups.items(), key=lambda item: (item[1]['volume'] * len(item[1]['boxes']), len(item[1]['boxes'])), reverse=True)
    # Flatten the sorted groups back into a list of boxes
    sorted_boxes = []
    for dims, group in sorted_groups:
        sorted_boxes.extend(group['boxes'])
    return sorted_boxes

def can_place_box(pallet, placed_boxes, box, x, y, z):
    """Check if the box can be placed at the given position."""
    # Check boundaries
    if (x + box.length > pallet.length or
        y + box.width > pallet.width or
        z + box.height > pallet.height):
        return False

    # Check overlap with other boxes
    for other in placed_boxes:
        if not (x + box.length <= other.position[0] or
                x >= other.position[0] + other.length or
                y + box.width <= other.position[1] or
                y >= other.position[1] + other.width or
                z + box.height <= other.position[2] or
                z >= other.position[2] + other.height):
            return False
    return True

def is_supported(placed_boxes, box, support_threshold=80):
    """Check if the box is supported by at least support_threshold% of its base area."""
    if box.position[2] == 0:
        return True, 100  # Base layer is always supported at 100%

    support_area = 0
    box_area = box.length * box.width

    for other in placed_boxes:
        if math.isclose(other.position[2] + other.height, box.position[2], abs_tol=1e-6):
            x_overlap = max(0, min(box.position[0] + box.length, other.position[0] + other.length) - max(box.position[0], other.position[0]))
            y_overlap = max(0, min(box.position[1] + box.width, other.position[1] + other.width) - max(box.position[1], other.position[1]))
            overlap_area = x_overlap * y_overlap
            support_area += overlap_area

    support_percentage = (support_area / box_area) * 100
    is_sufficient = support_percentage >= support_threshold
    return is_sufficient, support_percentage

def find_space_for_box(pallet, placed_boxes, box, layers):
    """Try to place the box in existing layers or create a new layer if necessary."""
    support_thresholds = [80, 75, 70, 65, 60]  # Thresholds to try
    # Try to place the box in existing layers
    for layer_z in sorted(layers):
        for rotation in box.get_rotations():
            box.length, box.width, box.height = rotation
            z = layer_z
            # Generate possible positions
            positions = generate_possible_positions(pallet, placed_boxes, box, z)
            for x, y in positions:
                box.position = (x, y, z)
                if can_place_box(pallet, placed_boxes, box, x, y, z):
                    for threshold in support_thresholds:
                        is_supported_flag, support_percentage = is_supported(placed_boxes, box, support_threshold=threshold)
                        if is_supported_flag:
                            # Place the box with this support threshold
                            box.support_threshold_used = threshold  # Store the threshold used
                            return True
                        else:
                            continue
                else:
                    continue
    # Try to create a new layer
    max_height = max([b.position[2] + b.height for b in placed_boxes], default=0)
    if max_height + box.height > pallet.height:
        return False  # Exceeds pallet height
    for rotation in box.get_rotations():
        box.length, box.width, box.height = rotation
        z = max_height
        # Generate possible positions
        positions = generate_possible_positions(pallet, placed_boxes, box, z)
        for x, y in positions:
            box.position = (x, y, z)
            if can_place_box(pallet, placed_boxes, box, x, y, z):
                for threshold in support_thresholds:
                    is_supported_flag, support_percentage = is_supported(placed_boxes, box, support_threshold=threshold)
                    if is_supported_flag:
                        # Place the box with this support threshold
                        layers.add(z)
                        box.support_threshold_used = threshold
                        return True
                    else:
                        continue
            else:
                continue
    return False

def generate_possible_positions(pallet, placed_boxes, box, z):
    """Generate possible positions for the box on the given layer z."""
    positions = []
    # Create a grid of positions with step size 1 unit
    x_range = range(0, int(pallet.length - box.length + 1), 1)
    y_range = range(0, int(pallet.width - box.width + 1), 1)

    # Prioritize positions starting from (0,0)
    for x in x_range:
        for y in y_range:
            positions.append((x, y))
    return positions

def calculate_volumetric_weight(pallet, placed_boxes):
    """Calculate the volumetric weight of the arrangement."""
    max_height = max([box.position[2] + box.height for box in placed_boxes], default=0)
    volumetric_weight = (pallet.length * pallet.width * max_height) / 6000  # Divided by 6000 as per standard volumetric weight calculation
    return volumetric_weight

# ----------------------------- #
#       Placement Function      #
# ----------------------------- #

def place_boxes(pallet, boxes):
    """Place all boxes onto the pallet."""
    placed_boxes = []
    layers = set([0])  # Start with the base layer at z = 0

    # Group boxes by dimensions and quantity
    groups = group_boxes_by_dimensions(boxes)
    # Sort boxes by group priority
    boxes_sorted = sort_boxes_by_group_priority(groups)

    for box in boxes_sorted:
        if not find_space_for_box(pallet, placed_boxes, box, layers):
            logging.error(f"Cannot place box {box.name}.")
            return []
        placed_boxes.append(box)
        box.placed = True
        logging.info(f"Placed {box.name} at position {box.position} with dimensions ({box.length}x{box.width}x{box.height}), support threshold used: {box.support_threshold_used}%")

    return placed_boxes

# ----------------------------- #
#       Visualization Function  #
# ----------------------------- #

def plot_pallet(pallet, placed_boxes):
    """Visualizes the pallet and placed boxes in 3D."""
    fig = go.Figure()

    # Add the pallet boundary as a transparent box
    pallet_vertices = [
        [0, 0, 0],
        [pallet.length, 0, 0],
        [pallet.length, pallet.width, 0],
        [0, pallet.width, 0],
        [0, 0, pallet.height],
        [pallet.length, 0, pallet.height],
        [pallet.length, pallet.width, pallet.height],
        [0, pallet.width, pallet.height]
    ]

    pallet_faces = [
        [0, 1, 2, 3],  # Bottom face
        [4, 5, 6, 7],  # Top face
        [0, 1, 5, 4],  # Front face
        [1, 2, 6, 5],  # Right face
        [2, 3, 7, 6],  # Back face
        [3, 0, 4, 7]   # Left face
    ]

    # Flatten the vertices for Mesh3d
    x_pallet = [pallet_vertices[vertex][0] for face in pallet_faces for vertex in face]
    y_pallet = [pallet_vertices[vertex][1] for face in pallet_faces for vertex in face]
    z_pallet = [pallet_vertices[vertex][2] for face in pallet_faces for vertex in face]

    fig.add_trace(go.Mesh3d(
        x=x_pallet,
        y=y_pallet,
        z=z_pallet,
        color='lightgrey',
        opacity=0.2,
        name='Pallet',
        showscale=False
    ))

    # Plot each placed box
    for box in placed_boxes:
        x0, y0, z0 = box.position
        x1, y1, z1 = x0 + box.length, y0 + box.width, z0 + box.height

        # Define the vertices of the box in 3D space
        vertices = [
            [x0, y0, z0],
            [x1, y0, z0],
            [x1, y1, z0],
            [x0, y1, z0],
            [x0, y0, z1],
            [x1, y0, z1],
            [x1, y1, z1],
            [x0, y1, z1],
        ]

        # Define the faces of the box
        faces = [
            [0, 1, 2, 3],  # Bottom
            [4, 5, 6, 7],  # Top
            [0, 1, 5, 4],  # Front
            [1, 2, 6, 5],  # Right
            [2, 3, 7, 6],  # Back
            [3, 0, 4, 7],  # Left
        ]

        x = [vertices[vertex][0] for face in faces for vertex in face]
        y = [vertices[vertex][1] for face in faces for vertex in face]
        z = [vertices[vertex][2] for face in faces for vertex in face]

        fig.add_trace(go.Mesh3d(
            x=x,
            y=y,
            z=z,
            color=box.color,
            opacity=0.7,
            name=box.name,
            hovertext=f'{box.name}: {box.length}x{box.width}x{box.height}, Support: {box.support_threshold_used}%',
            hoverinfo='text'
        ))

        # Add wireframe edges
        edge_x = []
        edge_y = []
        edge_z = []
        # Define the lines connecting the vertices
        edges = [
            [0, 1], [1, 2], [2, 3], [3, 0],  # Bottom face edges
            [4, 5], [5, 6], [6, 7], [7, 4],  # Top face edges
            [0, 4], [1, 5], [2, 6], [3, 7]   # Side edges
        ]
        for edge in edges:
            for vertex in edge:
                edge_x.append(vertices[vertex][0])
                edge_y.append(vertices[vertex][1])
                edge_z.append(vertices[vertex][2])
            edge_x.append(None)  # To break the line between edges
            edge_y.append(None)
            edge_z.append(None)

        fig.add_trace(go.Scatter3d(
            x=edge_x,
            y=edge_y,
            z=edge_z,
            mode='lines',
            line=dict(color='black', width=2),
            showlegend=False
        ))

    # Set plot limits and labels
    fig.update_layout(
        scene=dict(
            xaxis=dict(nticks=10, range=[0, pallet.length], title="Length"),
            yaxis=dict(nticks=10, range=[0, pallet.width], title="Width"),
            zaxis=dict(nticks=10, range=[0, pallet.height], title="Height"),
            aspectmode='data'
        ),
        width=800,
        height=600,
        margin=dict(r=20, l=10, b=10, t=10),
        legend=dict(title='Boxes')
    )

    return fig

# ----------------------------- #
#          Streamlit App        #
# ----------------------------- #

def main():
    # Configure logging
    logging.basicConfig(level=logging.INFO, format='%(message)s')

    st.title("Pallet Box Placement Tool")
    st.write("Enter the details of the boxes to arrange them on a pallet.")

    # Sidebar for Pallet Dimensions
    st.sidebar.header("Pallet Dimensions")
    pallet_length = st.sidebar.number_input("Pallet Length (units)", value=80)
    pallet_width = st.sidebar.number_input("Pallet Width (units)", value=60)
    pallet_height = st.sidebar.number_input("Pallet Height (units)", value=115)

    # Box Details Input
    st.header("Box Details")

    # Number of different box types
    num_boxes = st.number_input("Number of Different Box Types", min_value=1, max_value=20, value=1, step=1)

    box_details = []
    for i in range(int(num_boxes)):
        st.subheader(f"Box Type {i+1}")
        name = st.text_input(f"Name for Box {i+1}", value=f"Box {i+1}", key=f"name_{i}")
        length = st.number_input(f"Length for Box {i+1} (units)", value=40.0, step=1.0, key=f"length_{i}")
        width = st.number_input(f"Width for Box {i+1} (units)", value=30.0, step=1.0, key=f"width_{i}")
        height = st.number_input(f"Height for Box {i+1} (units)", value=10.0, step=1.0, key=f"height_{i}")
        weight = st.number_input(f"Weight for Box {i+1} (kg)", value=1.0, step=0.1, key=f"weight_{i}")
        quantity = st.number_input(f"Quantity for Box {i+1}", min_value=1, max_value=100, value=1, step=1, key=f"quantity_{i}")
        box_details.append({
            'name': name,
            'length': length,
            'width': width,
            'height': height,
            'weight': weight,
            'quantity': quantity
        })

    if st.button("Run"):
        # Instantiate Pallet
        pallet = Pallet(length=pallet_length, width=pallet_width, height=pallet_height, pallet_id=1)

        # Instantiate Boxes
        boxes = []
        box_id = 0
        for box_def in box_details:
            for _ in range(int(box_def['quantity'])):
                boxes.append(Box(
                    name=box_def['name'],
                    length=box_def['length'],
                    width=box_def['width'],
                    height=box_def['height'],
                    weight=box_def['weight'],
                    box_id=box_id
                ))
                box_id += 1

        # Place Boxes
        placed_boxes = place_boxes(pallet, boxes)

        if placed_boxes:
            volumetric_weight = calculate_volumetric_weight(pallet, placed_boxes)
            st.success("All boxes have been placed successfully.")
            st.write(f"**Volumetric Weight:** {volumetric_weight:.2f} kg")

            # Display placement details
            placement_details = []
            for box in placed_boxes:
                placement_details.append({
                    'Box Name': box.name,
                    'Position (x, y, z)': box.position,
                    'Dimensions (LxWxH)': f"{box.length}x{box.width}x{box.height}",
                    'Support Threshold Used (%)': box.support_threshold_used
                })
            st.subheader("Placement Details")
            st.table(placement_details)

            # Visualize the arrangement
            st.subheader("3D Visualization of Pallet Arrangement")
            fig = plot_pallet(pallet, placed_boxes)
            st.plotly_chart(fig, use_container_width=True)

        else:
            st.error("Failed to place all boxes. Please check the pallet dimensions or box sizes.")

if __name__ == "__main__":
    main()
