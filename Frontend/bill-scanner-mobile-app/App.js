import React, { useState, useRef } from 'react';
import { StyleSheet, Text, View, TouchableOpacity, Alert, SafeAreaView, ActivityIndicator, Image, Dimensions } from 'react-native';
import { CameraView, useCameraPermissions } from 'expo-camera';
import { Ionicons } from '@expo/vector-icons';

const { width } = Dimensions.get('window');

export default function App() {
  const [permission, requestPermission] = useCameraPermissions();
  const [mode, setMode] = useState('home'); 
  const [uploading, setUploading] = useState(false); 
  const cameraRef = useRef(null);

  const TUNNEL_URL = "https://ought-areas-area-citizenship.trycloudflare.com";

  if (!permission) return <View />;

  if (uploading) {
    return (
      <View style={styles.processingContainer}>
        <ActivityIndicator size="large" color="#74B9E1" />
        <Text style={styles.processingText}>Processing Bill...</Text>
        <Text style={styles.processingSubtext}>Running OCR and AI Analysis</Text>
      </View>
    );
  }

  if (mode === 'home') {
    return (
      <SafeAreaView style={styles.homeContainer}>
        {/* BACKGROUND TEXTURE/GRADIENT EFFECT */}
        <View style={styles.bgCircle} />
        
        <View style={styles.topSection}>
          <View style={styles.imageContainer}>
            <Image 
              source={require('./assets/illu.png')} 
              style={styles.logoImage} 
            />
          </View>
          
          <Text style={styles.title}>Bill Scanner</Text>
          
          <Text style={styles.introText}>
            Use this app to scan your bills. Our AI will read the text 
            and save the details to your computer automatically.
          </Text>
        </View>

        <View style={styles.bottomSection}>
          <TouchableOpacity 
            style={styles.mainButton} 
            onPress={() => permission.granted ? setMode('camera') : requestPermission()}
          >
            <Ionicons name="camera" size={24} color="white" style={{marginRight: 10}} />
            <Text style={styles.buttonText}>Capture</Text>
          </TouchableOpacity>
        </View>
      </SafeAreaView>
    );
  }

  const takeAndUpload = async () => {
    if (cameraRef.current) {
      try {
        const photo = await cameraRef.current.takePictureAsync({ quality: 0.5 });
        setUploading(true); 

        const formData = new FormData();
        formData.append('file', {
          uri: photo.uri,
          name: 'bill.jpg',
          type: 'image/jpeg',
        });

        const response = await fetch(`${TUNNEL_URL}/upload`, {
          method: 'POST',
          body: formData,
          headers: { 'Content-Type': 'multipart/form-data' },
        });

        const textData = await response.text();
        const result = JSON.parse(textData);

        if (response.ok) {
          Alert.alert("✅ Success", "Bill processed successfully!");
          setMode('home');
        } else {
          throw new Error(result.detail || "Server Error");
        }
      } catch (e) {
        Alert.alert("❌ Error", e.message);
      } finally {
        setUploading(false); 
      }
    }
  };

  return (
    <View style={styles.container}>
      <CameraView style={styles.camera} ref={cameraRef} facing="back">
        <TouchableOpacity style={styles.closeBtn} onPress={() => setMode('home')}>
          <Ionicons name="close-circle" size={45} color="white" />
        </TouchableOpacity>
        <TouchableOpacity style={styles.captureBtn} onPress={takeAndUpload}>
          <View style={styles.innerCircle} />
        </TouchableOpacity>
      </CameraView>
    </View>
  );
}

const styles = StyleSheet.create({
  processingContainer: { 
    flex: 1, 
    backgroundColor: 'white', 
    justifyContent: 'center', 
    alignItems: 'center' 
  },
  processingText: { 
    marginTop: 20, 
    fontSize: 22, 
    fontWeight: 'bold', 
    color: '#111827' 
  },
  processingSubtext: { 
    marginTop: 8, 
    fontSize: 14, 
    color: '#6B7280' 
  },

  homeContainer: { 
    flex: 1, 
    backgroundColor: '#F0F9FF', // Soft blue tint instead of plain white
    paddingHorizontal: 30 
  },

  // Gradient/Texture Trick
  bgCircle: {
    position: 'absolute',
    width: width * 1.5,
    height: width * 1.5,
    borderRadius: width,
    backgroundColor: '#FFFFFF',
    top: -width * 0.5,
    left: -width * 0.25,
    opacity: 0.8,
  },

  topSection: {
    marginTop: 180, // Balanced spacing
    alignItems: 'center',
    zIndex: 1,
  },
  title: { 
    fontSize: 32, 
    fontWeight: 'bold', 
    color: '#1F2937',
    marginBottom: 10
  },
  introText: {
    fontSize: 16,
    lineHeight: 24,
    color: '#4B5563',
    textAlign: 'center',
    paddingHorizontal: 10,
  },
  bottomSection: {
    flex: 1,
    justifyContent: 'flex-end', 
    marginBottom: 60,
    zIndex: 1,
  },
  mainButton: { 
    backgroundColor: '#74B9E1', // Matched to the blue in your illustration
    flexDirection: 'row', 
    paddingVertical: 18, 
    borderRadius: 30, // Rounded pill shape like the image
    alignItems: 'center',
    justifyContent: 'center',
    // Shadow for depth
    shadowColor: "#000",
    shadowOffset: { width: 0, height: 4 },
    shadowOpacity: 0.2,
    shadowRadius: 5,
    elevation: 8,
  },
  buttonText: { 
    color: 'white', 
    fontSize: 20, 
    fontWeight: 'bold' 
  },
  imageContainer: {
    width: 200,
    height: 200,
    marginBottom: 10,
    justifyContent: 'center',
    alignItems: 'center',
  },
  logoImage: {
    width: '100%',
    height: '100%',
    resizeMode: 'contain',
  },  

  container: { flex: 1, backgroundColor: 'black' },
  camera: { flex: 1, justifyContent: 'space-between', padding: 40 },
  closeBtn: { alignSelf: 'flex-start' },
  captureBtn: { 
    alignSelf: 'center', 
    width: 70, 
    height: 70, 
    borderRadius: 35, 
    borderWidth: 5, 
    borderColor: 'white', 
    justifyContent: 'center', 
    alignItems: 'center' 
  },
  innerCircle: { width: 50, height: 50, borderRadius: 25, backgroundColor: 'white' }
});