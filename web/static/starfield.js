// ============ Starfield Canvas Animation ============
(function() {
  const canvas = document.getElementById('star-canvas');
  if (!canvas) return;

  const ctx = canvas.getContext('2d');
  let width = window.innerWidth;
  let height = window.innerHeight;

  canvas.width = width;
  canvas.height = height;

  // 星星配置
  const STAR_COUNT = 300;
  const stars = [];

  // 初始化星星
  for (let i = 0; i < STAR_COUNT; i++) {
    stars.push({
      x: Math.random() * width,
      y: Math.random() * height,
      radius: Math.random() * 1.5 + 0.5,
      alpha: Math.random(),
      speed: Math.random() * 0.02 + 0.005,
      twinkleSpeed: Math.random() * 0.03 + 0.01,
      color: Math.random() > 0.7 ? '#a8c5ff' :
             Math.random() > 0.5 ? '#ffd4a3' : '#ffffff'
    });
  }

  // 流星
  let shootingStars = [];

  function createShootingStar() {
    if (Math.random() > 0.99 && shootingStars.length < 3) {
      shootingStars.push({
        x: Math.random() * width,
        y: Math.random() * height * 0.3,
        length: Math.random() * 100 + 60,
        speed: Math.random() * 15 + 10,
        angle: Math.PI / 4 + Math.random() * 0.2,
        alpha: 1
      });
    }
  }

  function drawNebula() {
    // 紫色星云 - 左下
    const grad1 = ctx.createRadialGradient(width * 0.2, height * 0.8, 0, width * 0.2, height * 0.8, width * 0.6);
    grad1.addColorStop(0, 'rgba(107, 70, 193, 0.4)');
    grad1.addColorStop(0.4, 'rgba(107, 70, 193, 0.1)');
    grad1.addColorStop(1, 'transparent');
    ctx.fillStyle = grad1;
    ctx.fillRect(0, 0, width, height);

    // 蓝色星云 - 右上
    const grad2 = ctx.createRadialGradient(width * 0.8, height * 0.2, 0, width * 0.8, height * 0.2, width * 0.5);
    grad2.addColorStop(0, 'rgba(59, 130, 246, 0.35)');
    grad2.addColorStop(0.4, 'rgba(59, 130, 246, 0.08)');
    grad2.addColorStop(1, 'transparent');
    ctx.fillStyle = grad2;
    ctx.fillRect(0, 0, width, height);

    // 青色微光 - 顶部
    const grad3 = ctx.createRadialGradient(width * 0.5, 0, 0, width * 0.5, 0, width * 0.4);
    grad3.addColorStop(0, 'rgba(6, 182, 212, 0.2)');
    grad3.addColorStop(1, 'transparent');
    ctx.fillStyle = grad3;
    ctx.fillRect(0, 0, width, height);
  }

  function drawStars() {
    stars.forEach(star => {
      // 闪烁
      star.alpha += star.twinkleSpeed;
      const brightness = Math.sin(star.alpha) * 0.5 + 0.5;

      // 绘制星星光晕
      const glow = ctx.createRadialGradient(star.x, star.y, 0, star.x, star.y, star.radius * 4);
      glow.addColorStop(0, star.color + Math.floor(brightness * 40).toString(16).padStart(2, '0'));
      glow.addColorStop(1, 'transparent');
      ctx.fillStyle = glow;
      ctx.beginPath();
      ctx.arc(star.x, star.y, star.radius * 4, 0, Math.PI * 2);
      ctx.fill();

      // 绘制星星核心
      ctx.fillStyle = star.color + Math.floor(brightness * 255).toString(16).padStart(2, '0');
      ctx.beginPath();
      ctx.arc(star.x, star.y, star.radius, 0, Math.PI * 2);
      ctx.fill();
    });
  }

  function drawShootingStars() {
    shootingStars.forEach((star, i) => {
      star.x += Math.cos(star.angle) * star.speed;
      star.y += Math.sin(star.angle) * star.speed;
      star.alpha -= 0.015;

      if (star.alpha <= 0) {
        shootingStars.splice(i, 1);
        return;
      }

      // 流星尾巴渐变
      const grad = ctx.createLinearGradient(
        star.x, star.y,
        star.x - Math.cos(star.angle) * star.length,
        star.y - Math.sin(star.angle) * star.length
      );
      grad.addColorStop(0, `rgba(255, 255, 255, ${star.alpha})`);
      grad.addColorStop(0.5, `rgba(168, 197, 255, ${star.alpha * 0.5})`);
      grad.addColorStop(1, 'transparent');

      ctx.strokeStyle = grad;
      ctx.lineWidth = 3;
      ctx.lineCap = 'round';
      ctx.beginPath();
      ctx.moveTo(star.x, star.y);
      ctx.lineTo(
        star.x - Math.cos(star.angle) * star.length,
        star.y - Math.sin(star.angle) * star.length
      );
      ctx.stroke();

      // 流星头部光点
      ctx.fillStyle = `rgba(255, 255, 255, ${star.alpha})`;
      ctx.beginPath();
      ctx.arc(star.x, star.y, 2, 0, Math.PI * 2);
      ctx.fill();
    });
  }

  function animate() {
    ctx.clearRect(0, 0, width, height);

    drawNebula();
    drawStars();
    createShootingStar();
    drawShootingStars();

    requestAnimationFrame(animate);
  }

  // 响应式
  window.addEventListener('resize', () => {
    width = window.innerWidth;
    height = window.innerHeight;
    canvas.width = width;
    canvas.height = height;
    // 重新分布星星
    stars.forEach(star => {
      if (star.x > width) star.x = Math.random() * width;
      if (star.y > height) star.y = Math.random() * height;
    });
  });

  animate();
})();
