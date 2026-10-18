<script setup lang="ts">
import { useI18n } from "vue-i18n";
const { locale } = useI18n();
const tx = (zh: string, en: string) => (locale.value === "zh" ? zh : en);
</script>

<template>
  <div class="help-page">
    <h1>{{ tx("帮助", "Help") }}</h1>
    
    <div class="help-sections">
      <div class="help-card">
        <h2>{{ tx("量尺指南", "Measurement Guide") }}</h2>
        <p>{{ tx("准确测量窗户尺寸对于确保百叶窗的完美安装至关重要。", "Accurate window measurement is essential for perfect shutter installation.") }}</p>
      </div>

      <div class="help-card">
        <h2>{{ tx("系列对比", "Series Comparison") }}</h2>
        <p>{{ tx("查看我们的产品系列详细对比，选择最适合您项目的系列。", "View our detailed product series comparison to choose the best fit for your project.") }}</p>
        <a href="https://verashading.com/products" target="_blank" rel="noopener">
          {{ tx("访问官网", "Visit Website") }} ↗
        </a>
      </div>

      <div class="help-card">
        <h2>{{ tx("联系我们", "Contact Us") }}</h2>
        <p>{{ tx("如有任何问题，请随时联系我们的团队。", "If you have any questions, feel free to contact our team.") }}</p>
        <p><strong>{{ tx("电话", "Phone") }}:</strong> 09 392 5656</p>
        <p><strong>{{ tx("邮箱", "Email") }}:</strong> office@verashading.com</p>
      </div>

      <div class="help-card">
        <h2>{{ tx("申请样品", "Request Samples") }}</h2>
        <p>{{ tx("想要查看实际样品？我们可以寄送产品样品供您参考。", "Want to see actual samples? We can send product samples for your reference.") }}</p>
      </div>
    </div>
  </div>
</template>

<style scoped>
.help-page {
  max-width: 1200px;
}

.help-page h1 {
  font-family: var(--font-display);
  font-size: 32px;
  font-weight: 600;
  margin: 0 0 32px;
}

.help-sections {
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(280px, 1fr));
  gap: 20px;
}

.help-card {
  padding: 24px;
  background: white;
  border: 1px solid var(--line);
  border-radius: 8px;
}

.help-card h2 {
  font-family: var(--font-display);
  font-size: 20px;
  font-weight: 600;
  margin: 0 0 12px;
  color: var(--cord);
}

.help-card p {
  margin: 8px 0;
  font-size: 15px;
  line-height: 1.6;
  color: rgba(27, 36, 33, 0.72);
}

.help-card a {
  display: inline-block;
  margin-top: 12px;
  color: var(--cord);
  text-decoration: none;
  font-weight: 600;
  font-size: 15px;
}

.help-card a:hover {
  text-decoration: underline;
}
</style>
