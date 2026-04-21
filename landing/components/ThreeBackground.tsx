"use client";
import { useEffect, useRef } from "react";
import * as THREE from "three";

export default function ThreeBackground() {
  const mountRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    const el = mountRef.current;
    if (!el) return;

    // Renderer
    const renderer = new THREE.WebGLRenderer({ antialias: true, alpha: true });
    renderer.setPixelRatio(Math.min(window.devicePixelRatio, 2));
    renderer.setSize(el.clientWidth, el.clientHeight);
    renderer.shadowMap.enabled = true;
    renderer.toneMapping = THREE.ACESFilmicToneMapping;
    renderer.toneMappingExposure = 1.2;
    el.appendChild(renderer.domElement);

    const scene = new THREE.Scene();
    const camera = new THREE.PerspectiveCamera(55, el.clientWidth / el.clientHeight, 0.1, 200);
    camera.position.set(0, 0, 28);

    // Lighting
    const ambient = new THREE.AmbientLight(0x10B981, 0.4);
    scene.add(ambient);
    const dirLight = new THREE.DirectionalLight(0xffffff, 1.2);
    dirLight.position.set(10, 20, 10);
    scene.add(dirLight);
    const greenPoint = new THREE.PointLight(0x10B981, 3, 60);
    greenPoint.position.set(-8, 5, 10);
    scene.add(greenPoint);
    const bluePoint = new THREE.PointLight(0x1a1aff, 1.5, 50);
    bluePoint.position.set(12, -8, 8);
    scene.add(bluePoint);

    // Glass orbs
    const orbData = [
      { pos: [-10, 4, -4], r: 3.5, color: 0x10B981, roughness: 0.0 },
      { pos: [10, -3, -6], r: 2.8, color: 0x059669, roughness: 0.0 },
      { pos: [0, 8, -10], r: 4.2, color: 0x34d399, roughness: 0.02 },
      { pos: [-14, -6, -8], r: 2.2, color: 0x10B981, roughness: 0.0 },
      { pos: [16, 6, -12], r: 3.0, color: 0x6ee7b7, roughness: 0.01 },
      { pos: [5, -10, -4], r: 1.8, color: 0x10B981, roughness: 0.0 },
    ];

    const orbs: { mesh: THREE.Mesh; speed: number; phase: number; axis: THREE.Vector3 }[] = [];

    orbData.forEach(d => {
      const geo = new THREE.SphereGeometry(d.r, 64, 64);
      const mat = new THREE.MeshPhysicalMaterial({
        color: d.color,
        transmission: 0.95,
        roughness: d.roughness,
        metalness: 0.0,
        ior: 1.45,
        thickness: d.r * 1.5,
        envMapIntensity: 1.5,
        clearcoat: 1.0,
        clearcoatRoughness: 0.0,
        transparent: true,
        opacity: 0.85,
      });
      const mesh = new THREE.Mesh(geo, mat);
      mesh.position.set(...d.pos as [number, number, number]);
      scene.add(mesh);
      orbs.push({
        mesh,
        speed: 0.0003 + Math.random() * 0.0004,
        phase: Math.random() * Math.PI * 2,
        axis: new THREE.Vector3(Math.random() - .5, Math.random() - .5, 0).normalize(),
      });
    });

    // Particle field
    const COUNT = 2400;
    const pGeo = new THREE.BufferGeometry();
    const pos = new Float32Array(COUNT * 3);
    const colors = new Float32Array(COUNT * 3);
    for (let i = 0; i < COUNT; i++) {
      pos[i * 3] = (Math.random() - .5) * 120;
      pos[i * 3 + 1] = (Math.random() - .5) * 80;
      pos[i * 3 + 2] = (Math.random() - .5) * 60 - 20;
      const t = Math.random();
      colors[i * 3] = t > .7 ? 0.063 : 0.02;
      colors[i * 3 + 1] = t > .7 ? 0.729 : 0.1;
      colors[i * 3 + 2] = t > .7 ? 0.506 : 0.08;
    }
    pGeo.setAttribute("position", new THREE.BufferAttribute(pos, 3));
    pGeo.setAttribute("color", new THREE.BufferAttribute(colors, 3));
    const pMat = new THREE.PointsMaterial({ size: 0.22, vertexColors: true, transparent: true, opacity: 0.55, sizeAttenuation: true });
    const particles = new THREE.Points(pGeo, pMat);
    scene.add(particles);

    // Mouse parallax
    let mx = 0, my = 0;
    const onMouse = (e: MouseEvent) => {
      mx = (e.clientX / window.innerWidth - .5) * 2;
      my = -(e.clientY / window.innerHeight - .5) * 2;
    };
    window.addEventListener("mousemove", onMouse);

    // Animate
    let frameId: number;
    const clock = new THREE.Clock();

    const animate = () => {
      frameId = requestAnimationFrame(animate);
      const t = clock.getElapsedTime();

      // Parallax camera
      camera.position.x += (mx * 3 - camera.position.x) * 0.03;
      camera.position.y += (my * 2 - camera.position.y) * 0.03;
      camera.lookAt(0, 0, 0);

      // Float orbs
      orbs.forEach(o => {
        const f = Math.sin(t * o.speed * 1000 + o.phase) * 0.8;
        o.mesh.position.y += Math.sin(t * 0.4 + o.phase) * 0.004;
        o.mesh.rotation.x += o.speed * 0.3;
        o.mesh.rotation.y += o.speed * 0.5;
        o.mesh.position.x += Math.cos(t * 0.25 + o.phase) * 0.002;
        void f;
      });

      // Drift particles
      particles.rotation.y += 0.00008;
      particles.rotation.x += 0.00004;

      renderer.render(scene, camera);
    };
    animate();

    const onResize = () => {
      renderer.setSize(el.clientWidth, el.clientHeight);
      camera.aspect = el.clientWidth / el.clientHeight;
      camera.updateProjectionMatrix();
    };
    window.addEventListener("resize", onResize);

    return () => {
      cancelAnimationFrame(frameId);
      window.removeEventListener("mousemove", onMouse);
      window.removeEventListener("resize", onResize);
      renderer.dispose();
      if (el.contains(renderer.domElement)) el.removeChild(renderer.domElement);
    };
  }, []);

  return (
    <div ref={mountRef} style={{
      position: "fixed", inset: 0, zIndex: 0, pointerEvents: "none",
    }} />
  );
}
