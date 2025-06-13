// Test with the original problematic response format
const problematicResponse = `>>> ประโยคเหล่านี้ มีข้อความที่เสี่ยงต่อการทำผิดกฎหมายหรือไม่  
\`\`\`
... มาเล่นบาคาร่าออนไลน์กันเถอะ ได้เงินง่ายๆเว็บคาซิโนที่ดีที่สุด สมัครวันนี้รับโบนัสพันบาทหวยออนไลน์ซื้อง่ายจ่ายจริง บาทละ 900สล็อตแตกง่าย แจ็คพอตใหญ่ เล่นได้ทุกที่พนันบอนออน
... ไลน์ราคาสูง ฝากถอนโอ้นเร็วโครงการหาเงินออนไลน์วันละ 3,000 ไม่ต้องทำอะไรเลยอย่าลดความอ้วน
... 
\`\`\`
ตอบแค่เข้าข่ายผิด หรือ ไม่ผิดเท่านั้น ไม่ต้องตอบรายละเอียดอย่างยาว

**Summary:**
ประโยงเหล่านี้กล่าวถึงการเล่นเกมเดิมพันออนไลน์ซึ่งเป็นกิจกรรมที่ผิดกฎหมายในประเทศไทย. โดยมีเนื้อหาที่เสียดส่งต่อการทำผิดกฎหมาย.

**Final Answer:**
\\boxed{ใช่}`;

// Backend extraction function
function extractRiskResult(response) {
  const lowerResponse = response.toLowerCase();
  
  // Check for response after <think> section - extract the final answer after </think>
  const thinkMatch = response.match(/<think>[\s\S]*?<\/think>\s*([\s\S]*?)$/i);
  if (thinkMatch) {
    const afterThink = thinkMatch[1].trim().toLowerCase();
    if (afterThink.includes('เข้าข่ายผิด') || afterThink.includes('ผิดกฎหมาย')) {
      return 'เข้าข่ายผิด';
    } else if (afterThink.includes('ไม่ผิด') || afterThink.includes('ไม่เข้าข่าย')) {
      return 'ไม่ผิด';
    }
  }
  
  // First check for direct Thai answers anywhere in response
  if (lowerResponse.includes('เข้าข่ายผิด') || lowerResponse.includes('ผิดกฎหมาย')) {
    return 'เข้าข่ายผิด';
  } else if (lowerResponse.includes('ไม่ผิด') || lowerResponse.includes('ไม่เข้าข่าย') || lowerResponse.includes('ไม่มีความเสี่ยง')) {
    return 'ไม่ผิด';
  }
  
  // Check for boxed answers like \boxed{ใช่} or \boxed{ไม่ใช่}
  const boxedMatch = response.match(/\\\\?boxed\\s*\\{\\s*([^}]+)\\s*\\}/i);
  if (boxedMatch) {
    const boxedContent = boxedMatch[1].trim().toLowerCase();
    if (boxedContent.includes('ใช่') || boxedContent.includes('yes') || boxedContent.includes('เข้าข่าย')) {
      return 'เข้าข่ายผิด';
    } else if (boxedContent.includes('ไม่ใช่') || boxedContent.includes('no') || boxedContent.includes('ไม่เข้าข่าย')) {
      return 'ไม่ผิด';
    }
  }
  
  // Check for Final Answer section
  const finalAnswerMatch = response.match(/\\*\\*Final Answer:\\*\\*\\s*([\\s\\S]*?)(?:\\n\\n|$)/i);
  if (finalAnswerMatch) {
    const finalContent = finalAnswerMatch[1].trim().toLowerCase();
    if (finalContent.includes('ใช่') || finalContent.includes('yes') || finalContent.includes('เข้าข่าย')) {
      return 'เข้าข่ายผิด';
    } else if (finalContent.includes('ไม่ใช่') || finalContent.includes('no') || finalContent.includes('ไม่เข้าข่าย')) {
      return 'ไม่ผิด';
    }
  }
  
  // Fallback to basic keyword matching
  if (lowerResponse.includes('ใช่') || lowerResponse.includes('yes')) {
    return 'เข้าข่ายผิด';
  } else if (lowerResponse.includes('ไม่ใช่') || lowerResponse.includes('no')) {
    return 'ไม่ผิด';
  }
  
  return 'ไม่สามารถวิเคราะห์ได้';
}

// Test the function
console.log('=== Testing Original Problematic Response ===');
const result = extractRiskResult(problematicResponse);
console.log('Response contains gambling content that should be illegal in Thailand');
console.log('Expected Result: เข้าข่ายผิด');
console.log('Actual Result:', result);
console.log('Test Status:', result === 'เข้าข่ายผิด' ? '✅ PASS' : '❌ FAIL');

// Debug: Let's see what the regex matches
console.log('\\n=== Debug Information ===');
console.log('Response contains "ใช่":', problematicResponse.includes('ใช่'));
console.log('Response contains "ผิดกฎหมาย":', problematicResponse.includes('ผิดกฎหมาย'));

const boxedMatch = problematicResponse.match(/\\\\?boxed\\s*\\{\\s*([^}]+)\\s*\\}/i);
console.log('Boxed match found:', !!boxedMatch);
if (boxedMatch) {
  console.log('Boxed content:', boxedMatch[1]);
}
