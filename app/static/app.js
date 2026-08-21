import * as THREE from 'three';
import { OrbitControls } from 'three/addons/controls/OrbitControls.js';
import { GLTFLoader } from 'three/addons/loaders/GLTFLoader.js';
import { STLLoader } from 'three/addons/loaders/STLLoader.js';

/* =========================================================================
   ATS Engineering AI — Text-to-CAD Workbench Application Logic
   ========================================================================= */

class CADWorkbench {
  constructor() {
    this.currentProject = null;
    this.currentVersion = null;
    this.projects = [];
    this.sessionId = `session_${Math.random().toString(36).substring(2, 9)}`;
    
    // Viewport & Shading State
    this.displayMode = 'edges'; // 'edges', 'solid', 'wireframe', 'xray', 'transparent', 'section'
    this.isOrthographic = false;
    this.helpersState = {
      grid: true,
      axes: true,
      'plane-xy': true,
      'plane-xz': false,
      'plane-yz': false,
      bbox: false
    };

    // Three.js State
    this.currentMesh = null;
    this.edgeMesh = null;
    this.bboxHelper = null;
    this.highlightMesh = null;
    this.selectedFaceIndex = null;
    this.clippingPlanes = [];

    // Theme
    this.currentTheme = localStorage.getItem('cad_workbench_theme') || 'light';
    this.expandedProjects = new Set();

    this.initDOM();
    this.initThreeJS();
    this.initGizmo();
    this.initWebSocket();
    this.initTheme();
    this.loadProjects();
  }

  /* -------------------------------------------------------------------------
     1. DOM Initializations & Event Listeners
     ------------------------------------------------------------------------- */
  initDOM() {
    this.canvas = document.getElementById('cad-canvas');
    this.gizmoCanvas = document.getElementById('axis-gizmo');
    this.viewportContainer = document.getElementById('viewportContainer');

    // Toolbar elements
    this.themeToggleBtn = document.getElementById('themeToggleBtn');
    this.themeIcon = document.getElementById('themeIcon');
    this.projectSelect = document.getElementById('projectSelect');
    this.versionBadge = document.getElementById('versionBadge');
    this.projectTreeList = document.getElementById('projectTreeList');
    this.projectCount = document.getElementById('projectCount');
    this.versionList = document.getElementById('versionList');
    this.versionCount = document.getElementById('versionCount');
    this.fileList = document.getElementById('fileList');

    // Prompt bar elements
    this.promptInput = document.getElementById('promptInput');
    this.btnGenerate = document.getElementById('btnGenerate');
    this.generateBtnText = document.getElementById('generateBtnText');
    this.generateBtnIcon = document.getElementById('generateBtnIcon');
    this.btnClearPrompt = document.getElementById('btnClearPrompt');
    this.btnAttachRef = document.getElementById('btnAttachRef');

    // Viewport Toolbar Buttons
    this.btnFit = document.getElementById('btnFit');
    this.btnResetCam = document.getElementById('btnResetCam');
    this.btnToggleCam = document.getElementById('btnToggleCam');

    // Empty state
    this.emptyState = document.getElementById('viewportEmptyState');
    this.samplePromptChip = document.getElementById('samplePromptChip');
    this.btnEmptyGenerate = document.getElementById('btnEmptyGenerate');

    // Modals
    this.settingsModal = document.getElementById('settingsModal');
    this.codeModal = document.getElementById('codeModal');
    this.newProjectModal = document.getElementById('newProjectModal');

    // Bind Event Listeners
    this.bindEvents();
  }

  bindEvents() {
    // Theme toggle
    this.themeToggleBtn.addEventListener('click', () => {
      this.currentTheme = this.currentTheme === 'dark' ? 'light' : 'dark';
      this.applyTheme(this.currentTheme);
    });

    // Project selection
    this.projectSelect.addEventListener('change', (e) => {
      this.selectProject(e.target.value);
    });

    // Fullscreen
    document.getElementById('fullscreenBtn').addEventListener('click', () => {
      if (!document.fullscreenElement) {
        document.documentElement.requestFullscreen();
      } else {
        document.exitFullscreen();
      }
    });

    // Prompt bar input auto-resize & enter to submit
    this.promptInput.addEventListener('input', () => {
      this.promptInput.style.height = 'auto';
      this.promptInput.style.height = Math.min(this.promptInput.scrollHeight, 120) + 'px';
    });

    this.promptInput.addEventListener('keydown', (e) => {
      if (e.key === 'Enter' && !e.shiftKey) {
        e.preventDefault();
        this.handleGenerate();
      }
    });

    this.btnGenerate.addEventListener('click', () => this.handleGenerate());
    this.btnClearPrompt.addEventListener('click', () => {
      this.promptInput.value = '';
      this.promptInput.style.height = '38px';
    });

    if (this.btnAttachRef) {
      this.btnAttachRef.addEventListener('click', () => {
        alert('Attach Reference: Engineering drawings (.dxf, .png, .pdf) or STEP reference files can be linked here.');
      });
    }

    if (this.btnEmptyGenerate) {
      this.btnEmptyGenerate.addEventListener('click', () => {
        this.promptInput.focus();
      });
    }

    // Template chips
    document.querySelectorAll('.chip-btn').forEach(btn => {
      btn.addEventListener('click', () => {
        this.promptInput.value = btn.dataset.prompt;
        this.promptInput.focus();
      });
    });

    // Viewport Camera Presets
    this.btnFit.addEventListener('click', () => this.fitCameraToBounds());
    this.btnResetCam.addEventListener('click', () => this.resetCamera());
    this.btnToggleCam.addEventListener('click', () => this.toggleCameraMode());

    document.querySelectorAll('.cam-preset').forEach(btn => {
      btn.addEventListener('click', () => this.setCameraPreset(btn.dataset.preset));
    });

    // Display modes
    document.querySelectorAll('.mode-btn').forEach(btn => {
      btn.addEventListener('click', () => {
        document.querySelectorAll('.mode-btn').forEach(b => b.classList.remove('active'));
        btn.classList.add('active');
        this.setDisplayMode(btn.dataset.mode);
      });
    });

    // Helper toggles
    document.querySelectorAll('.helper-btn').forEach(btn => {
      btn.addEventListener('click', () => {
        const helper = btn.dataset.helper;
        this.helpersState[helper] = !this.helpersState[helper];
        btn.classList.toggle('active', this.helpersState[helper]);
        this.updateHelpers();
      });
    });

    // Inspector Tabs
    document.querySelectorAll('.tab-btn').forEach(btn => {
      btn.addEventListener('click', () => {
        document.querySelectorAll('.tab-btn').forEach(b => b.classList.remove('active'));
        document.querySelectorAll('.tab-content').forEach(c => c.classList.remove('active'));
        btn.classList.add('active');
        const tabId = `tab-${btn.dataset.tab}`;
        const target = document.getElementById(tabId);
        if (target) target.classList.add('active');
      });
    });

    // Download Buttons
    document.getElementById('btnDownloadStep').addEventListener('click', () => this.downloadCurrentFile('model.step'));
    document.getElementById('btnDownloadStl').addEventListener('click', () => this.downloadCurrentFile('model.stl'));
    document.getElementById('btnDownloadGlb').addEventListener('click', () => this.downloadCurrentFile('model.glb'));
    document.getElementById('btnDownloadPy').addEventListener('click', () => this.downloadCurrentFile('model.py'));

    // Project action buttons
    document.getElementById('btnNewProject').addEventListener('click', () => this.openModal('newProjectModal'));
    document.getElementById('btnNewModel').addEventListener('click', () => {
      this.promptInput.value = '';
      this.promptInput.placeholder = 'Describe a new CAD model...';
      this.promptInput.focus();
    });

    document.getElementById('btnDuplicate').addEventListener('click', () => this.duplicateProject());
    document.getElementById('btnRestoreVersion').addEventListener('click', () => this.restoreCurrentVersion());
    document.getElementById('btnDeleteVersion').addEventListener('click', () => this.deleteCurrentVersion());

    // Settings Modal
    document.getElementById('settingsBtn').addEventListener('click', () => this.openModal('settingsModal'));
    document.getElementById('btnSaveSettings').addEventListener('click', () => {
      localStorage.setItem('cad_vllm_base', document.getElementById('settingVllmBase').value);
      localStorage.setItem('cad_workstation_ip', document.getElementById('settingWorkstationIp').value);
      this.closeModal('settingsModal');
    });

    // Modals close buttons
    document.querySelectorAll('.close-modal').forEach(btn => {
      btn.addEventListener('click', () => this.closeModal(btn.dataset.modal));
    });

    // New Project Confirm
    document.getElementById('btnConfirmCreateProject').addEventListener('click', () => {
      const name = document.getElementById('newProjectNameInput').value.trim() || 'New Mounting Part';
      this.createNewProject(name);
      this.closeModal('newProjectModal');
    });

    // Copy code button in Code modal
    document.getElementById('btnCopyCode').addEventListener('click', () => {
      const text = document.getElementById('codeContent').innerText;
      navigator.clipboard.writeText(text).then(() => {
        alert('Copied to clipboard!');
      });
    });

    // File item click in sidebar
    this.fileList.addEventListener('click', (e) => {
      const item = e.target.closest('.file-item');
      if (!item) return;
      const fileName = item.dataset.file;
      this.handleFileItemClick(fileName);
    });

    // Window resize
    window.addEventListener('resize', () => this.onWindowResize());
  }

  /* -------------------------------------------------------------------------
     2. Three.js Viewport & Lighting Setup
     ------------------------------------------------------------------------- */
  initThreeJS() {
    const width = this.viewportContainer.clientWidth;
    const height = this.viewportContainer.clientHeight;

    // Scene
    this.scene = new THREE.Scene();

    // Cameras
    const aspect = width / height;
    this.perspCamera = new THREE.PerspectiveCamera(45, aspect, 0.1, 5000);
    this.perspCamera.position.set(160, 140, 200);

    const d = 150;
    this.orthoCamera = new THREE.OrthographicCamera(-d * aspect, d * aspect, d, -d, 0.1, 5000);
    this.orthoCamera.position.set(160, 140, 200);

    this.activeCamera = this.perspCamera;

    // WebGL Renderer
    this.renderer = new THREE.WebGLRenderer({
      canvas: this.canvas,
      antialias: true,
      alpha: true,
      preserveDrawingBuffer: true
    });
    this.renderer.setSize(width, height);
    this.renderer.setPixelRatio(Math.min(window.devicePixelRatio, 2));
    this.renderer.shadowMap.enabled = true;
    this.renderer.shadowMap.type = THREE.PCFSoftShadowMap;
    this.renderer.localClippingEnabled = true;

    // OrbitControls
    this.controls = new OrbitControls(this.activeCamera, this.canvas);
    this.controls.enableDamping = true;
    this.controls.dampingFactor = 0.08;
    this.controls.screenSpacePanning = true;
    this.controls.target.set(0, 0, 0);

    // Studio Lighting
    this.setupLighting();

    // CAD Helpers: Engineering Grid, Triad, Reference Planes
    this.setupHelpers();

    // Raycaster for Selection
    this.raycaster = new THREE.Raycaster();
    this.mouse = new THREE.Vector2();
    this.setupRaycasting();

    // Animation Render Loop
    this.animate = this.animate.bind(this);
    requestAnimationFrame(this.animate);
  }

  setupLighting() {
    this.ambientLight = new THREE.AmbientLight(0xffffff, 0.65);
    this.scene.add(this.ambientLight);

    this.dirLight1 = new THREE.DirectionalLight(0xffffff, 0.85);
    this.dirLight1.position.set(200, 300, 200);
    this.dirLight1.castShadow = true;
    this.scene.add(this.dirLight1);

    this.dirLight2 = new THREE.DirectionalLight(0x90b0e0, 0.45);
    this.dirLight2.position.set(-200, -100, -200);
    this.scene.add(this.dirLight2);

    this.hemiLight = new THREE.HemisphereLight(0xffffff, 0x444455, 0.4);
    this.scene.add(this.hemiLight);
  }

  setupHelpers() {
    this.helpersGroup = new THREE.Group();
    this.scene.add(this.helpersGroup);

    // 1. Engineering Grid (200x200mm, 20 divisions = 10mm major lines)
    const gridSize = 300;
    const gridDivs = 30;
    this.gridHelper = new THREE.GridHelper(gridSize, gridDivs, 0x3b82f6, 0x272e3f);
    this.gridHelper.position.y = -0.05;
    this.helpersGroup.add(this.gridHelper);

    // 2. Coordinate Origin Triad
    this.axesHelper = new THREE.AxesHelper(40);
    this.axesHelper.renderOrder = 2;
    this.helpersGroup.add(this.axesHelper);

    // 3. Selectable Reference Planes (XY, XZ, YZ)
    const planeSize = 200;
    const createPlane = (normal, color, name) => {
      const geom = new THREE.PlaneGeometry(planeSize, planeSize);
      const mat = new THREE.MeshBasicMaterial({
        color: color,
        transparent: true,
        opacity: 0.08,
        side: THREE.DoubleSide,
        depthWrite: false
      });
      const mesh = new THREE.Mesh(geom, mat);
      mesh.name = name;

      // Add border wire
      const edges = new THREE.EdgesGeometry(geom);
      const lineMat = new THREE.LineBasicMaterial({ color: color, transparent: true, opacity: 0.35 });
      const wire = new THREE.LineSegments(edges, lineMat);
      mesh.add(wire);
      return mesh;
    };

    // XY Plane (Horizontal / Z-up in build123d coordinate space)
    this.planeXY = createPlane(new THREE.Vector3(0, 0, 1), 0x3b82f6, 'plane-xy');
    this.planeXY.rotation.x = Math.PI / 2;
    this.helpersGroup.add(this.planeXY);

    // XZ Plane (Vertical front)
    this.planeXZ = createPlane(new THREE.Vector3(0, 1, 0), 0x10b981, 'plane-xz');
    this.helpersGroup.add(this.planeXZ);

    // YZ Plane (Vertical side)
    this.planeYZ = createPlane(new THREE.Vector3(1, 0, 0), 0xf97316, 'plane-yz');
    this.planeYZ.rotation.y = Math.PI / 2;
    this.helpersGroup.add(this.planeYZ);

    this.updateHelpers();
  }

  updateHelpers() {
    this.gridHelper.visible = this.helpersState.grid;
    this.axesHelper.visible = this.helpersState.axes;
    this.planeXY.visible = this.helpersState['plane-xy'];
    this.planeXZ.visible = this.helpersState['plane-xz'];
    this.planeYZ.visible = this.helpersState['plane-yz'];
    if (this.bboxHelper) {
      this.bboxHelper.visible = this.helpersState.bbox;
    }
  }

  /* -------------------------------------------------------------------------
     3. 3D Orientation Axis Gizmo (Corner Indicator)
     ------------------------------------------------------------------------- */
  initGizmo() {
    this.gizmoRenderer = new THREE.WebGLRenderer({
      canvas: this.gizmoCanvas,
      antialias: true,
      alpha: true
    });
    this.gizmoRenderer.setSize(90, 90);
    this.gizmoRenderer.setPixelRatio(window.devicePixelRatio);

    this.gizmoScene = new THREE.Scene();
    this.gizmoCamera = new THREE.PerspectiveCamera(50, 1, 0.1, 100);
    this.gizmoCamera.position.set(0, 0, 50);

    // Create Axis arrows for Gizmo
    const createAxis = (dir, color, label) => {
      const arrow = new THREE.ArrowHelper(dir, new THREE.Vector3(0, 0, 0), 18, color, 4, 3);
      this.gizmoScene.add(arrow);
      return arrow;
    };

    createAxis(new THREE.Vector3(1, 0, 0), 0xef4444, 'X'); // Red
    createAxis(new THREE.Vector3(0, 1, 0), 0x10b981, 'Y'); // Green
    createAxis(new THREE.Vector3(0, 0, 1), 0x3b82f6, 'Z'); // Blue
  }

  /* -------------------------------------------------------------------------
     4. Raycasting & Geometry Selection Inspection
     ------------------------------------------------------------------------- */
  setupRaycasting() {
    this.selectionBadge = document.getElementById('selectionBadge');
    this.selectionType = document.getElementById('selectionType');
    this.selectionNormal = document.getElementById('selectionNormal');
    this.selectionArea = document.getElementById('selectionArea');

    this.canvas.addEventListener('pointerdown', (e) => {
      // Only handle left click on canvas
      if (e.button !== 0) return;
      const rect = this.canvas.getBoundingClientRect();
      this.mouse.x = ((e.clientX - rect.left) / rect.width) * 2 - 1;
      this.mouse.y = -((e.clientY - rect.top) / rect.height) * 2 + 1;

      this.raycaster.setFromCamera(this.mouse, this.activeCamera);
      if (!this.currentMesh) return;

      const intersects = this.raycaster.intersectObject(this.currentMesh, true);
      if (intersects.length > 0) {
        const hit = intersects[0];
        this.selectFace(hit);
      } else {
        this.clearSelection();
      }
    });
  }

  selectFace(hit) {
    if (!hit || !hit.face) return;
    const normal = hit.face.normal.clone();
    normal.transformDirection(hit.object.matrixWorld);

    // Calculate triangle area
    const geom = hit.object.geometry;
    let area = 0;
    if (geom && geom.attributes.position && hit.faceIndex !== undefined) {
      const pos = geom.attributes.position;
      const a = new THREE.Vector3().fromBufferAttribute(pos, hit.face.a);
      const b = new THREE.Vector3().fromBufferAttribute(pos, hit.face.b);
      const c = new THREE.Vector3().fromBufferAttribute(pos, hit.face.c);
      const ab = new THREE.Vector3().subVectors(b, a);
      const ac = new THREE.Vector3().subVectors(c, a);
      area = (ab.cross(ac).length() / 2).toFixed(2);
    }

    // Update Selection Badge
    this.selectionType.innerText = `FACE #${hit.faceIndex}`;
    this.selectionNormal.innerText = `Normal: [${normal.x.toFixed(2)}, ${normal.y.toFixed(2)}, ${normal.z.toFixed(2)}]`;
    this.selectionArea.innerText = `Face Area: ${area} mm²`;
    this.selectionBadge.style.display = 'block';

    // Update Inspector Tab Geometry
    document.getElementById('selElemName').innerText = `Face #${hit.faceIndex}`;
    document.getElementById('selElemNormal').innerText = `[${normal.x.toFixed(2)}, ${normal.y.toFixed(2)}, ${normal.z.toFixed(2)}]`;
    document.getElementById('selElemArea').innerText = `${area} mm²`;
  }

  clearSelection() {
    if (this.selectionBadge) this.selectionBadge.style.display = 'none';
    document.getElementById('selElemName').innerText = 'None';
    document.getElementById('selElemNormal').innerText = '--';
    document.getElementById('selElemArea').innerText = '-- mm²';
  }

  /* -------------------------------------------------------------------------
     5. Model Loading (GLB / STL) & CAD Shading
     ------------------------------------------------------------------------- */
  async loadModelFromURL(url, isStl = false) {
    this.emptyState.style.display = 'none';
    this.clearSelection();

    if (this.currentMesh) {
      this.scene.remove(this.currentMesh);
      if (this.currentMesh.geometry) this.currentMesh.geometry.dispose();
      this.currentMesh = null;
    }
    if (this.edgeMesh) {
      this.scene.remove(this.edgeMesh);
      if (this.edgeMesh.geometry) this.edgeMesh.geometry.dispose();
      this.edgeMesh = null;
    }
    if (this.bboxHelper) {
      this.scene.remove(this.bboxHelper);
      this.bboxHelper = null;
    }

    const onGeomLoaded = (geom) => {
      geom.computeVertexNormals();
      geom.computeBoundingBox();
      const box = geom.boundingBox;
      const sizeX = box.max.x - box.min.x;
      const sizeY = box.max.y - box.min.y;
      const sizeZ = box.max.z - box.min.z;
      const maxDim = Math.max(sizeX, sizeY, sizeZ);
      
      // Auto-detect unit: if bounding dimensions are in meters (< 2.0), scale to mm
      if (maxDim < 2.0 && maxDim > 0.00001) {
        geom.scale(1000, 1000, 1000);
      }
      
      geom.center();
      this.applyGeometryToScene(geom);
    };

    const cleanUrl = (url || '').split('?')[0].toLowerCase();
    const isStlFile = isStl || cleanUrl.endsWith('.stl') || url.includes('.stl');

    try {
      if (isStlFile) {
        const loader = new STLLoader();
        loader.load(url, onGeomLoaded, undefined, (err) => {
          console.warn('STL load error:', err);
        });
      } else {
        const loader = new GLTFLoader();
        loader.load(url, (gltf) => {
          let targetGeom = null;
          gltf.scene.traverse((child) => {
            if (child.isMesh && !targetGeom) {
              targetGeom = child.geometry.clone();
            }
          });
          if (targetGeom) {
            onGeomLoaded(targetGeom);
          } else if (this.currentVersion && this.currentVersion.stl_url) {
            this.loadModelFromURL(this.currentVersion.stl_url, true);
          }
        }, undefined, (err) => {
          console.warn('GLB load error, trying STL fallback:', err);
          if (this.currentVersion && this.currentVersion.stl_url) {
            this.loadModelFromURL(this.currentVersion.stl_url, true);
          }
        });
      }
    } catch (e) {
      console.error('Model load exception:', e);
    }
  }

  applyGeometryToScene(geometry) {
    // Primary Solid Material
    this.cadMaterial = new THREE.MeshStandardMaterial({
      color: this.currentTheme === 'dark' ? 0x94a3b8 : 0x64748b,
      metalness: 0.15,
      roughness: 0.35,
      side: THREE.DoubleSide
    });

    this.currentMesh = new THREE.Mesh(geometry, this.cadMaterial);
    this.currentMesh.castShadow = true;
    this.currentMesh.receiveShadow = true;
    this.scene.add(this.currentMesh);

    // Sharp CAD Edges
    const edgesGeom = new THREE.EdgesGeometry(geometry, 25);
    const edgeColor = this.currentTheme === 'dark' ? 0x1e293b : 0x0f172a;
    this.edgeMaterial = new THREE.LineBasicMaterial({ color: edgeColor, linewidth: 1.5 });
    this.edgeMesh = new THREE.LineSegments(edgesGeom, this.edgeMaterial);
    this.scene.add(this.edgeMesh);

    // Bounding Box Helper
    this.bboxHelper = new THREE.BoxHelper(this.currentMesh, 0x06b6d4);
    this.bboxHelper.visible = this.helpersState.bbox;
    this.scene.add(this.bboxHelper);

    // Update display mode materials
    this.applyDisplayMode();

    // Fit camera
    this.fitCameraToBounds();
  }

  setDisplayMode(mode) {
    this.displayMode = mode;
    this.applyDisplayMode();
  }

  applyDisplayMode() {
    if (!this.currentMesh || !this.cadMaterial) return;

    // Reset properties
    this.cadMaterial.wireframe = false;
    this.cadMaterial.transparent = false;
    this.cadMaterial.opacity = 1.0;
    this.cadMaterial.depthWrite = true;
    this.cadMaterial.clippingPlanes = [];
    if (this.edgeMesh) this.edgeMesh.visible = false;

    switch (this.displayMode) {
      case 'edges':
        this.cadMaterial.color.setHex(this.currentTheme === 'dark' ? 0x94a3b8 : 0x64748b);
        if (this.edgeMesh) this.edgeMesh.visible = true;
        break;
      case 'solid':
        this.cadMaterial.color.setHex(this.currentTheme === 'dark' ? 0xa0aec0 : 0x718096);
        break;
      case 'wireframe':
        this.cadMaterial.wireframe = true;
        break;
      case 'xray':
        this.cadMaterial.transparent = true;
        this.cadMaterial.opacity = 0.45;
        this.cadMaterial.depthWrite = false;
        if (this.edgeMesh) this.edgeMesh.visible = true;
        break;
      case 'transparent':
        this.cadMaterial.transparent = true;
        this.cadMaterial.opacity = 0.7;
        this.cadMaterial.roughness = 0.1;
        this.cadMaterial.metalness = 0.8;
        if (this.edgeMesh) this.edgeMesh.visible = true;
        break;
      case 'section':
        // Section cutaway along Z plane
        const clipPlane = new THREE.Plane(new THREE.Vector3(0, 0, -1), 0);
        this.cadMaterial.clippingPlanes = [clipPlane];
        this.cadMaterial.clipShadows = true;
        if (this.edgeMesh) this.edgeMesh.visible = true;
        break;
    }
  }

  /* -------------------------------------------------------------------------
     6. Camera Views & Presets
     ------------------------------------------------------------------------- */
  fitCameraToBounds() {
    if (!this.currentMesh) return;
    const box = new THREE.Box3().setFromObject(this.currentMesh);
    const center = box.getCenter(new THREE.Vector3());
    const size = box.getSize(new THREE.Vector3());
    const maxDim = Math.max(size.x, size.y, size.z, 50);

    const fov = this.perspCamera.fov * (Math.PI / 180);
    let cameraZ = Math.abs(maxDim / 2 / Math.tan(fov / 2)) * 1.8;

    this.perspCamera.position.set(center.x + cameraZ * 0.7, center.y + cameraZ * 0.6, center.z + cameraZ * 0.8);
    this.perspCamera.lookAt(center);

    this.controls.target.copy(center);
    this.controls.update();
  }

  resetCamera() {
    this.perspCamera.position.set(160, 140, 200);
    this.controls.target.set(0, 0, 0);
    this.controls.update();
  }

  toggleCameraMode() {
    this.isOrthographic = !this.isOrthographic;
    this.activeCamera = this.isOrthographic ? this.orthoCamera : this.perspCamera;
    this.controls.object = this.activeCamera;
    this.btnToggleCam.innerText = this.isOrthographic ? 'Orthographic' : 'Perspective';
    this.controls.update();
  }

  setCameraPreset(preset) {
    const dist = 220;
    const target = this.controls.target || new THREE.Vector3(0, 0, 0);
    switch (preset) {
      case 'iso':
        this.activeCamera.position.set(target.x + dist * 0.7, target.y + dist * 0.7, target.z + dist * 0.7);
        break;
      case 'front':
        this.activeCamera.position.set(target.x, target.y, target.z + dist);
        break;
      case 'back':
        this.activeCamera.position.set(target.x, target.y, target.z - dist);
        break;
      case 'left':
        this.activeCamera.position.set(target.x - dist, target.y, target.z);
        break;
      case 'right':
        this.activeCamera.position.set(target.x + dist, target.y, target.z);
        break;
      case 'top':
        this.activeCamera.position.set(target.x, target.y + dist, target.z + 0.001);
        break;
      case 'bottom':
        this.activeCamera.position.set(target.x, target.y - dist, target.z + 0.001);
        break;
    }
    this.activeCamera.lookAt(target);
    this.controls.update();
  }

  /* -------------------------------------------------------------------------
     7. Project & Version Management
     ------------------------------------------------------------------------- */
  async loadProjects(preferredProjectId = null, autoSelectLatest = true) {
    try {
      const res = await fetch('/api/projects');
      if (res.ok) {
        this.projects = await res.json();
        this.renderProjectSelect();
        
        const targetId = preferredProjectId || (this.currentProject ? this.currentProject.project_id : (this.projects[0]?.project_id));
        if (targetId && autoSelectLatest) {
          await this.selectProject(targetId);
        } else if (targetId) {
          this.currentProject = this.projects.find(p => p.project_id === targetId) || this.projects[0];
          if (this.currentProject) {
            this.expandedProjects.add(this.currentProject.project_id);
            this.projectSelect.value = this.currentProject.project_id;
            document.getElementById('propProjectName').innerText = this.currentProject.name;
            this.renderProjectTree();
          }
        }
      }
    } catch (e) {
      console.warn('Error loading projects:', e);
    }
  }

  renderProjectSelect() {
    this.projectSelect.innerHTML = '';
    this.projects.forEach(p => {
      const opt = document.createElement('option');
      opt.value = p.project_id;
      opt.innerText = p.name;
      this.projectSelect.appendChild(opt);
    });
  }

  async selectProject(projectId) {
    this.currentProject = this.projects.find(p => p.project_id === projectId) || this.projects[0];
    if (!this.currentProject) return;

    this.expandedProjects.add(this.currentProject.project_id);
    this.projectSelect.value = this.currentProject.project_id;
    document.getElementById('propProjectName').innerText = this.currentProject.name;

    // Render Project Tree
    this.renderProjectTree();

    // Select latest version of this project
    if (this.currentProject.versions && this.currentProject.versions.length > 0) {
      const latest = this.currentProject.versions[this.currentProject.versions.length - 1];
      this.selectVersion(latest);
    } else {
      this.emptyState.style.display = 'flex';
      this.versionBadge.innerText = 'v000';
    }
  }

  renderProjectTree() {
    if (this.projectCount) {
      this.projectCount.innerText = this.projects.length;
    }

    if (!this.projectTreeList) return;
    this.projectTreeList.innerHTML = '';

    if (!this.projects || this.projects.length === 0) {
      this.projectTreeList.innerHTML = '<div class="project-versions-empty">No projects found. Click + New to create one.</div>';
      return;
    }

    this.projects.forEach(p => {
      const isCurrent = this.currentProject && this.currentProject.project_id === p.project_id;
      const isExpanded = this.expandedProjects.has(p.project_id) || isCurrent;
      const versions = p.versions || [];

      const node = document.createElement('div');
      node.className = `project-tree-node ${isCurrent ? 'active-project' : ''}`;
      node.dataset.projectId = p.project_id;

      // Folder Header
      const header = document.createElement('div');
      header.className = 'project-folder-header';
      header.innerHTML = `
        <div class="folder-left">
          <span class="folder-chevron ${isExpanded ? 'expanded' : ''}">▶</span>
          <span class="folder-icon">
            <svg width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
              <path d="M22 19a2 2 0 0 1-2 2H4a2 2 0 0 1-2-2V5a2 2 0 0 1 2-2h5l2 3h9a2 2 0 0 1 2 2z"/>
            </svg>
          </span>
          <span class="folder-name" title="${p.name}">${p.name}</span>
        </div>
        <div class="folder-right">
          <span class="folder-badge" title="${versions.length} versions">${versions.length}</span>
        </div>
      `;

      // Versions Sublist Container
      const sublist = document.createElement('div');
      sublist.className = 'project-versions-sublist';
      sublist.style.display = isExpanded ? 'flex' : 'none';

      if (versions.length === 0) {
        sublist.innerHTML = '<div class="project-versions-empty">No design iterations yet</div>';
      } else {
        [...versions].reverse().forEach(v => {
          const isVersionActive = isCurrent && this.currentVersion && this.currentVersion.version_id === v.version_id;
          const vEl = document.createElement('div');
          vEl.className = `version-item ${isVersionActive ? 'active' : ''}`;
          vEl.dataset.versionId = v.version_id;
          vEl.innerHTML = `
            <div class="version-left">
              <span class="version-tag">${v.version_label}</span>
              <span class="version-prompt-text" title="${v.prompt || 'CAD Solid'}">${v.prompt || 'CAD Solid'}</span>
            </div>
            <span class="version-meta">${v.duration_ms ? (v.duration_ms / 1000).toFixed(1) + 's' : ''}</span>
          `;
          vEl.addEventListener('click', (e) => {
            e.stopPropagation();
            if (!isCurrent) {
              this.selectProject(p.project_id).then(() => {
                this.selectVersion(v);
              });
            } else {
              this.selectVersion(v);
            }
          });
          sublist.appendChild(vEl);
        });
      }

      header.addEventListener('click', () => {
        if (!isCurrent) {
          this.expandedProjects.add(p.project_id);
          this.selectProject(p.project_id);
        } else {
          // Toggle current project expansion
          if (this.expandedProjects.has(p.project_id)) {
            this.expandedProjects.delete(p.project_id);
            sublist.style.display = 'none';
            header.querySelector('.folder-chevron')?.classList.remove('expanded');
          } else {
            this.expandedProjects.add(p.project_id);
            sublist.style.display = 'flex';
            header.querySelector('.folder-chevron')?.classList.add('expanded');
          }
        }
      });

      node.appendChild(header);
      node.appendChild(sublist);
      this.projectTreeList.appendChild(node);
    });
  }

  selectVersion(version) {
    this.currentVersion = version;
    this.versionBadge.innerText = version.version_label;
    document.getElementById('propVersion').innerText = version.version_label;
    document.getElementById('propExplanation').innerText = version.prompt || (version.plan && version.plan.explanation) || '';
    document.getElementById('propGenTime').innerText = `${version.duration_ms || '--'} ms`;

    // Highlight active in version list across tree
    document.querySelectorAll('.project-versions-sublist .version-item').forEach(el => {
      const isTarget = el.dataset.versionId === version.version_id;
      el.classList.toggle('active', isTarget);
    });

    // Populate Inspector Geometry & Validation
    if (version.validation) {
      const v = version.validation;
      document.getElementById('geomVolume').innerText = `${v.volume_mm3.toLocaleString()} mm³`;
      document.getElementById('geomArea').innerText = `${(v.surface_area_mm2 || 0).toLocaleString()} mm²`;
      if (v.bounding_box) {
        document.getElementById('geomBBox').innerText = `${v.bounding_box.size_x} × ${v.bounding_box.size_y} × ${v.bounding_box.size_z} mm`;
        document.getElementById('geomMinBounds').innerText = `[${v.bounding_box.min_x}, ${v.bounding_box.min_y}, ${v.bounding_box.min_z}]`;
        document.getElementById('geomMaxBounds').innerText = `[${v.bounding_box.max_x}, ${v.bounding_box.max_y}, ${v.bounding_box.max_z}]`;
      }
      document.getElementById('geomFaceCount').innerText = v.face_count;
      document.getElementById('geomEdgeCount').innerText = v.edge_count;
      document.getElementById('geomVertexCount').innerText = v.vertex_count;
      document.getElementById('geomSolidCount').innerText = v.solid_count || 1;
      document.getElementById('valAuditMessage').innerText = v.message || 'Verification complete.';
    }

    // Populate Feature Tree
    if (version.plan) {
      document.getElementById('propTargetTool').innerText = version.plan.tool || 'inventor.create_box';
      const tree = document.getElementById('featureTreeList');
      tree.innerHTML = '';

      // Base solid item
      const baseItem = document.createElement('div');
      baseItem.className = 'feature-item';
      baseItem.innerHTML = `
        <span style="display: flex; align-items: center; gap: 6px;">
          <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M21 16V8a2 2 0 0 0-1-1.73l-7-4a2 2 0 0 0-2 0l-7 4A2 2 0 0 0 3 8v8a2 2 0 0 0 1 1.73l7 4a2 2 0 0 0 2 0l7-4A2 2 0 0 0 21 16z"/></svg>
          Base Solid (${version.plan.shape_type})
        </span>
        <span class="version-meta">${version.plan.length_mm || 100}x${version.plan.width_mm || 60}x${version.plan.height_mm || 20}</span>
      `;
      tree.appendChild(baseItem);

      // Hole features
      if (version.plan.holes && version.plan.holes.length > 0) {
        version.plan.holes.forEach((h, idx) => {
          const holeItem = document.createElement('div');
          holeItem.className = 'feature-item';
          holeItem.innerHTML = `
            <span style="display: flex; align-items: center; gap: 6px;">
              <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><circle cx="12" cy="12" r="9"/><circle cx="12" cy="12" r="3"/></svg>
              Hole Feature #${idx + 1}
            </span>
            <span class="version-meta">Ø${h.diameter_mm}mm (${h.count || 1}x ${h.pattern_type})</span>
          `;
          tree.appendChild(holeItem);
        });
      }
    }

    // Update prompt placeholder
    if (version.prompt) {
      this.promptInput.placeholder = `Modify model (e.g. 'Increase hole diameter to 10 mm', 'Add 2 mm chamfer')...`;
    } else {
      this.promptInput.placeholder = `Describe your mechanical CAD design in natural language (e.g. dimensions, mounting holes, slots, shafts, brackets)...`;
    }

    // Load 3D Model into Viewport (prefer STL for direct millimeter geometry)
    let modelUrl = (version.stl_url && !version.stl_url.includes('None'))
      ? version.stl_url
      : (version.glb_url || `/api/projects/${this.currentProject.project_id}/versions/${version.version_label}/files/model.stl`);
    const sep = modelUrl.includes('?') ? '&' : '?';
    this.loadModelFromURL(`${modelUrl}${sep}t=${Date.now()}`, modelUrl.endsWith('.stl') || modelUrl.includes('.stl'));
  }

  /* -------------------------------------------------------------------------
     8. Text-to-CAD Generation & Modification Pipeline
     ------------------------------------------------------------------------- */
  async handleGenerate() {
    const promptText = this.promptInput.value.trim();
    if (!promptText) return;

    this.btnGenerate.disabled = true;
    this.generateBtnText.innerText = 'GENERATING...';

    this.updatePipelineStage('planning');

    const projectId = this.currentProject ? this.currentProject.project_id : 'proj_default';
    const payload = {
      prompt: promptText,
      project_id: projectId,
      session_id: this.sessionId,
      workstation_ip: localStorage.getItem('cad_workstation_ip') || '192.168.11.150',
      context: {
        previous_version: this.currentVersion ? this.currentVersion.version_label : null,
        previous_prompt: this.currentVersion ? this.currentVersion.prompt : null,
        previous_code: (this.currentVersion && this.currentVersion.plan) ? this.currentVersion.plan.python_script : null
      }
    };

    const startTime = performance.now();
    try {
      const res = await fetch(`/api/projects/${projectId}/versions`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(payload)
      });

      const data = await res.json();
      const totalDur = (performance.now() - startTime).toFixed(0);

      if (data.success) {
        this.updatePipelineStage('complete');
        document.getElementById('metricGemma').innerText = `${data.gemma_duration_ms || '--'} ms`;
        document.getElementById('metricBuild').innerText = `${data.cad_build_duration_ms || '--'} ms`;
        document.getElementById('metricTotal').innerText = `${totalDur} ms`;

        // Refresh project data and select new version
        await this.loadProjects(projectId, false);
        const p = this.projects.find(x => x.project_id === projectId);
        if (p && p.versions && p.versions.length > 0) {
          const latestVersion = p.versions[p.versions.length - 1];
          this.selectVersion(latestVersion);
        }

        this.promptInput.value = '';
        this.promptInput.style.height = '38px';
      } else {
        this.updatePipelineStage('error');
        alert(`CAD Generation Failed: ${data.message || 'Unknown error'}`);
      }
    } catch (e) {
      console.error('Generation request failed:', e);
      this.updatePipelineStage('error');
      alert(`Network error contacting CAD service: ${e}`);
    } finally {
      this.btnGenerate.disabled = false;
      this.generateBtnText.innerText = 'GENERATE CAD';
    }
  }

  updatePipelineStage(stage) {
    const stages = ['planning', 'generating', 'building', 'validating', 'exporting', 'complete'];
    const currentIdx = stages.indexOf(stage);

    document.querySelectorAll('.pipe-step').forEach(step => {
      const s = step.dataset.step;
      const idx = stages.indexOf(s);
      step.classList.remove('active', 'complete');
      if (idx < currentIdx) {
        step.classList.add('complete');
      } else if (idx === currentIdx) {
        step.classList.add('active');
      }
    });
  }

  /* -------------------------------------------------------------------------
     9. Actions, Files & Downloads
     ------------------------------------------------------------------------- */
  async createNewProject(name) {
    try {
      const res = await fetch('/api/projects', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ name: name })
      });
      if (res.ok) {
        const newProj = await res.json();
        await this.loadProjects();
        this.selectProject(newProj.project_id);
      }
    } catch (e) {
      console.error('Create project failed:', e);
    }
  }

  async duplicateProject() {
    if (!this.currentProject) return;
    const newName = `${this.currentProject.name} (Copy)`;
    await this.createNewProject(newName);
  }

  async restoreCurrentVersion() {
    if (!this.currentProject || !this.currentVersion) return;
    try {
      const res = await fetch(`/api/projects/${this.currentProject.project_id}/versions/${this.currentVersion.version_label}/restore`, {
        method: 'POST'
      });
      if (res.ok) {
        await this.loadProjects();
        const p = this.projects.find(x => x.project_id === this.currentProject.project_id);
        if (p && p.versions) {
          this.selectVersion(p.versions[p.versions.length - 1]);
        }
      }
    } catch (e) {
      console.error('Restore failed:', e);
    }
  }

  async deleteCurrentVersion() {
    if (!this.currentProject || !this.currentVersion) return;
    if (!confirm(`Delete version ${this.currentVersion.version_label}?`)) return;

    try {
      const res = await fetch(`/api/projects/${this.currentProject.project_id}/versions/${this.currentVersion.version_label}`, {
        method: 'DELETE'
      });
      if (res.ok) {
        await this.loadProjects();
        const p = this.projects.find(x => x.project_id === this.currentProject.project_id);
        if (p) this.selectProject(p.project_id);
      }
    } catch (e) {
      console.error('Delete failed:', e);
    }
  }

  async handleFileItemClick(fileName) {
    if (!this.currentProject || !this.currentVersion) return;
    const fileUrl = `/api/projects/${this.currentProject.project_id}/versions/${this.currentVersion.version_label}/files/${fileName}`;

    if (fileName.endsWith('.glb') || fileName.endsWith('.stl')) {
      this.loadModelFromURL(fileUrl, fileName.endsWith('.stl'));
    } else if (fileName.endsWith('.py') || fileName.endsWith('.json')) {
      try {
        const res = await fetch(fileUrl);
        const text = await res.text();
        document.getElementById('codeModalTitle').innerText = `${this.currentVersion.version_label} / ${fileName}`;
        document.getElementById('codeContent').innerText = text;
        this.openModal('codeModal');
      } catch (e) {
        console.error('File load error:', e);
      }
    } else if (fileName.endsWith('.step')) {
      this.downloadCurrentFile('model.step');
    }
  }

  downloadCurrentFile(fileName) {
    if (!this.currentProject || !this.currentVersion) {
      alert('Please generate a CAD model first.');
      return;
    }
    const fileUrl = `/api/projects/${this.currentProject.project_id}/versions/${this.currentVersion.version_label}/files/${fileName}`;
    const link = document.createElement('a');
    link.href = fileUrl;
    link.download = `${this.currentProject.name.replace(/\s+/g, '_')}_${this.currentVersion.version_label}_${fileName}`;
    document.body.appendChild(link);
    link.click();
    document.body.removeChild(link);
  }

  /* -------------------------------------------------------------------------
     10. Theme System
     ------------------------------------------------------------------------- */
  initTheme() {
    this.applyTheme(this.currentTheme);
  }

  applyTheme(theme) {
    this.currentTheme = theme;
    document.documentElement.setAttribute('data-theme', theme);
    localStorage.setItem('cad_workbench_theme', theme);

    const btn = document.getElementById('themeToggleBtn');
    if (btn) {
      if (theme === 'dark') {
        btn.innerHTML = `
          <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
            <circle cx="12" cy="12" r="5"></circle>
            <line x1="12" y1="1" x2="12" y2="3"></line>
            <line x1="12" y1="21" x2="12" y2="23"></line>
            <line x1="4.22" y1="4.22" x2="5.64" y2="5.64"></line>
            <line x1="18.36" y1="18.36" x2="19.78" y2="19.78"></line>
            <line x1="1" y1="12" x2="3" y2="12"></line>
            <line x1="21" y1="12" x2="23" y2="12"></line>
            <line x1="4.22" y1="19.78" x2="5.64" y2="18.36"></line>
            <line x1="18.36" y1="5.64" x2="19.78" y2="4.22"></line>
          </svg>
        `;
      } else {
        btn.innerHTML = `
          <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
            <path d="M21 12.79A9 9 0 1 1 11.21 3 7 7 0 0 0 21 12.79z"></path>
          </svg>
        `;
      }
    }

    if (this.gridHelper) {
      this.gridHelper.material.color.setHex(theme === 'dark' ? 0x3b82f6 : 0x0284c7);
    }
    if (this.edgeMaterial) {
      this.edgeMaterial.color.setHex(theme === 'dark' ? 0x1e293b : 0x0f172a);
    }
    if (this.cadMaterial) {
      this.cadMaterial.color.setHex(theme === 'dark' ? 0x94a3b8 : 0x64748b);
    }
  }

  /* -------------------------------------------------------------------------
     11. WebSocket Connection for Real-Time Logs & Status
     ------------------------------------------------------------------------- */
  initWebSocket() {
    const protocol = window.location.protocol === 'https:' ? 'wss:' : 'ws:';
    const wsUrl = `${protocol}//${window.location.host}/ws/${this.sessionId}`;
    
    try {
      this.ws = new WebSocket(wsUrl);
      this.ws.onmessage = (event) => {
        try {
          const msg = JSON.parse(event.data);
          if (msg.event === 'stage' && msg.data) {
            this.updatePipelineStage(msg.data.stage);
          }
        } catch (e) {}
      };
    } catch (e) {
      console.warn('WebSocket init notice:', e);
    }
  }

  /* -------------------------------------------------------------------------
     12. Modal Helpers & Render Loop
     ------------------------------------------------------------------------- */
  openModal(modalId) {
    const el = document.getElementById(modalId);
    if (el) el.classList.add('active');
  }

  closeModal(modalId) {
    const el = document.getElementById(modalId);
    if (el) el.classList.remove('active');
  }

  onWindowResize() {
    const width = this.viewportContainer.clientWidth;
    const height = this.viewportContainer.clientHeight;
    const aspect = width / height;

    this.perspCamera.aspect = aspect;
    this.perspCamera.updateProjectionMatrix();

    const d = 150;
    this.orthoCamera.left = -d * aspect;
    this.orthoCamera.right = d * aspect;
    this.orthoCamera.top = d;
    this.orthoCamera.bottom = -d;
    this.orthoCamera.updateProjectionMatrix();

    this.renderer.setSize(width, height);
  }

  animate() {
    requestAnimationFrame(this.animate);
    this.controls.update();
    this.renderer.render(this.scene, this.activeCamera);

    // Sync Orientation Gizmo rotation
    if (this.gizmoCamera && this.activeCamera) {
      this.gizmoCamera.position.copy(this.activeCamera.position);
      this.gizmoCamera.position.sub(this.controls.target);
      this.gizmoCamera.position.setLength(50);
      this.gizmoCamera.lookAt(0, 0, 0);
      this.gizmoRenderer.render(this.gizmoScene, this.gizmoCamera);
    }
  }
}

// Instantiate Workbench when DOM is ready
window.addEventListener('DOMContentLoaded', () => {
  window.cadWorkbench = new CADWorkbench();
});
