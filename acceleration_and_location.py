import streamlit as st
import pandas as pd
import numpy as np
from scipy.signal import find_peaks, butter, filtfilt, welch
import matplotlib.pyplot as plt
from geopy.distance import geodesic
import folium
from streamlit_folium import st_folium

# Function to read location data 
def read_location_data(file):
    try:
        raw_data = file.read().decode('utf-8-sig')
        lines = raw_data.strip().split('\n')

        if len(lines) < 2:
            st.error("The location data is not in the expected format.")
            return None

        header = lines[0].replace('"', '').split(',')
        data_lines = [line.split(',') for line in lines[1:]]

        loc_data = pd.DataFrame(data_lines, columns=header)
        for col in header[1:]:
            loc_data[col] = pd.to_numeric(loc_data[col], errors='coerce')

        expected_columns = 8
        if loc_data.shape[1] != expected_columns:
            st.error(f"Expected {expected_columns} columns but got {loc_data.shape[1]} columns.")
            return None

        return loc_data

    except Exception as e:
        st.error(f"Error processing location data: {e}")
        return None

# Loading CSV files
uploaded_file_acc = st.file_uploader("Upload linear acceleration data", type="csv")
uploaded_file_loc = st.file_uploader("Upload location data", type="csv")

if uploaded_file_acc and uploaded_file_loc:
    try:
        acc_data = pd.read_csv(uploaded_file_acc)
        st.write("Raw Acceleration Data:", acc_data.head())

        loc_data = read_location_data(uploaded_file_loc)

        if loc_data is not None:
            st.write("Cleaned Location Data:", loc_data.head())
            
            # Processing Acceleration Data
            try:
                acc_x = pd.to_numeric(acc_data["Linear Acceleration x (m/s^2)"], errors='coerce')
                acc_y = pd.to_numeric(acc_data["Linear Acceleration y (m/s^2)"], errors='coerce')
                acc_z = pd.to_numeric(acc_data["Linear Acceleration z (m/s^2)"], errors='coerce')

                # Acceleration component calculation (standard deviation)
                std_dev_x = acc_x.std()
                std_dev_y = acc_y.std()
                std_dev_z = acc_z.std()

                # Selecting the best component for analysis
                best_component = 'x' if std_dev_x > std_dev_y and std_dev_x > std_dev_z else 'y' if std_dev_y > std_dev_z else 'z'
                st.write(f"Selected Component for Analysis: {best_component.upper()}")

                # Low-pass Butterworth filter applied to the acceleration data
                fs = 50  # Sampling frequency (Hz), for human motion
                cutoff = 3  # Cutoff frequency (Hz), for human walk
                b, a = butter(4, cutoff / (0.5 * fs), btype='low')
                filtered_acc = filtfilt(b, a, acc_x if best_component == 'x' else acc_y if best_component == 'y' else acc_z)

                # Counting Steps/Peaks in Filtered Acceleration Data
                peaks, _ = find_peaks(filtered_acc, distance=fs / 2)  # Half a second between steps
                num_steps_peaks = len(peaks)

                # Fourier Analysis
                freqs, psd = welch(filtered_acc, fs=fs, nperseg=512)  # Power Spectral Density
                dominant_freq = freqs[np.argmax(psd)]
                num_steps_fft = int(dominant_freq * (len(filtered_acc) / fs))

                # Processing Location Data
                st.write("Processing Location Data...")
                if 'Latitude (°)' in loc_data.columns and 'Longitude (°)' in loc_data.columns:
                    # Extracting latitude and longitude for distance calculation
                    latitudes = loc_data['Latitude (°)'].values
                    longitudes = loc_data['Longitude (°)'].values
                    speeds = loc_data['Velocity (m/s)'].values

                    # Debugging output for latitudes and longitudes
                    st.write("Latitudes:", latitudes)
                    st.write("Longitudes:", longitudes)
                    st.write("Speeds:", speeds)

                    # Calculating total distance, average speed
                    distances = [
                        geodesic((latitudes[i], longitudes[i]), (latitudes[i + 1], longitudes[i + 1])).meters 
                        for i in range(len(latitudes) - 1)
                    ]
                    total_distance = sum(distances)
                    avg_speed = np.mean(speeds)

                    step_length = total_distance / num_steps_peaks if num_steps_peaks > 0 else 0
                    
                    # Displaying Results
                    st.write(f"Number of Steps (Peak Detection): {num_steps_peaks}")
                    st.write(f"Number of Steps (Fourier Analysis): {num_steps_fft}")
                    st.write(f"Average Speed (from GPS data): {avg_speed:.2f} m/s")
                    st.write(f"Traveled Distance (from GPS data): {total_distance:.2f} meters")
                    st.write(f"Step Length: {step_length:.2f} meters")
                    
                    # Plotting Results
                    st.write("Filtered Acceleration Data (for Step Detection)")
                    fig1, ax1 = plt.subplots(figsize=(10, 5)) 
                    ax1.plot(filtered_acc, label=f'Filtered Acceleration ({best_component.upper()})', color='blue')
                    ax1.plot(peaks, filtered_acc[peaks], "x", label='Detected Steps', color='red')
                    ax1.set_xlabel("Sample")
                    ax1.set_ylabel("Acceleration (m/s²)")
                    ax1.set_title("Filtered Acceleration Data with Detected Steps")
                    ax1.legend()
                    st.pyplot(fig1)
                    
                    # Power Spectral Density plot
                    st.write("Power Spectral Density of the Acceleration Data")
                    fig2, ax2 = plt.subplots(figsize=(10, 5))
                    ax2.semilogy(freqs, psd)
                    ax2.set_xlabel("Frequency (Hz)")
                    ax2.set_ylabel("Power/Frequency (dB/Hz)")
                    ax2.set_title("Power Spectral Density")
                    st.pyplot(fig2)
                    
            except Exception as e:
                st.error(f"Error processing acceleration data: {e}")
            
            # Prepare Folium Map
            if 'Latitude (°)' in loc_data.columns and 'Longitude (°)' in loc_data.columns:
                # Initializing the map at the mean latitude and longitude
                map_center = [loc_data['Latitude (°)'].mean(), loc_data['Longitude (°)'].mean()]
                folium_map = folium.Map(location=map_center, zoom_start=15)

                # Adding markers with popup information
                for idx, row in loc_data.iterrows():
                    folium.Marker(
                        location=[row['Latitude (°)'], row['Longitude (°)']],
                        popup=(
                            f"Time: {row['Time (s)']} s<br>"
                            f"Speed: {row['Velocity (m/s)']} m/s<br>"
                            f"Height: {row['Height (m)']} m"
                        ),
                        icon=folium.Icon(color='blue')
                    ).add_to(folium_map)

                # Drawing lines to show the path
                folium.PolyLine(
                    locations=list(zip(loc_data['Latitude (°)'], loc_data['Longitude (°)'])),
                    color='blue',
                    weight=2.5,
                    opacity=1
                ).add_to(folium_map)

                # Displaying the map in Streamlit
                st_folium(folium_map, width=700, height=500)

    except pd.errors.ParserError as e:
        st.error(f"Error parsing CSV: {e}")
    except Exception as e:
        st.error(f"An unexpected error occurred: {e}")
