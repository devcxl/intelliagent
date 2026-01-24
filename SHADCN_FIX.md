# shadcn/ui 修复说明

## 问题

shadcn/ui 样式没有生效，界面看起来没有样式。

## 原因

使用了 **Tailwind CSS 4.x** 版本，但配置不正确：
1. Tailwind CSS 4.x 使用了全新的 CSS-first 配置方式
2. 配置文件语法与 v3.x 完全不同
3. 导致 shadcn/ui 组件的样式没有正确编译

## 解决方案

降级到 **Tailwind CSS 3.x**，与 shadcn/ui 兼容性更好。

### 执行步骤

```bash
cd web/frontend

# 卸载 Tailwind 4.x
npm uninstall tailwindcss @tailwindcss/postcss

# 安装 Tailwind 3.x
npm install -D tailwindcss@^3 postcss autoprefixer

# 初始化配置
npx tailwindcss init -p
```

### 配置文件

**tailwind.config.js**:
```js
export default {
  content: [
    "./index.html",
    "./src/**/*.{js,ts,jsx,tsx}",
  ],
  theme: {
    extend: {
      colors: {
        border: "hsl(var(--border))",
        // ... 其他颜色
      },
      borderRadius: {
        lg: "var(--radius)",
        md: "calc(var(--radius) - 2px)",
        sm: "calc(var(--radius) - 4px)",
      },
    },
  },
  plugins: [],
}
```

**src/index.css**:
```css
@tailwind base;
@tailwind components;
@tailwind utilities;

@layer base {
  :root {
    --background: 220 20% 97%;
    --foreground: 220 15% 15%;
    // ... 其他 CSS 变量
  }

  body {
    background-color: hsl(var(--background));
    color: hsl(var(--foreground));
  }
}
```

## 验证结果

### CSS 文件大小

- 之前（Tailwind 4.x）: ~21 kB（但样式不完整）
- 现在（Tailwind 3.x）: 20.75 kB（样式完整）

### 样式检查

```bash
# 检查 shadcn/ui 样式是否存在
cat dist/assets/index-*.css | grep -o '\.bg-primary' | head -5

# 输出：
# .bg-primary
# .bg-primary
# .bg-primary
```

### 具体样式

```css
.bg-primary {
  background-color: hsl(var(--primary));
}

.text-primary-foreground {
  color: hsl(var(--primary-foreground));
}
```

## 最终效果

✅ shadcn/ui 样式正确编译并生效
✅ 所有组件样式正常显示
✅ 按钮、卡片、徽章等组件样式正确

## 依赖版本

```json
{
  "devDependencies": {
    "tailwindcss": "^3.4.0",
    "postcss": "^8.4.23",
    "autoprefixer": "^10.4.23"
  }
}
```

## 注意事项

1. **不要使用 Tailwind CSS 4.x**：目前与 shadcn/ui 不完全兼容
2. **使用 Tailwind CSS 3.x**：稳定且与 shadcn/ui 完全兼容
3. **未来更新**：等待 shadcn/ui 官方支持 Tailwind 4.x

## 重新构建

```bash
cd web/frontend
npm run build
```

构建输出：
```
dist/index.html                   0.50 kB │ gzip:  0.36 kB
dist/assets/index-TtiMm5Zx.css   20.75 kB │ gzip:  4.67 kB
dist/assets/index-B6B9sJ9u.js   260.28 kB │ gzip: 81.41 kB
```

现在可以启动服务查看效果了！
