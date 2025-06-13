// Test the parser with the actual Ollama response format
const testResponse = `<think>
Okay, let's see. The user provided a block of Thai text and is asking whether it contains content that could be illegal. They want a simple answer: either "เข้าข่ายผิด" (likely illegal) or "ไม่ผิด" (not illegal), without any detailed explanation.

First, I need to understand the Thai text. Let me read through it again. The text seems to be a mix of phrases, possibly from a radio show or a script. There are mentions of "โจโจสั่งนะครับ" which might be a name or a term. Then there's talk about "บรรยากาศสบายสบาย" (comfortable atmosphere), "ช่วงวันพระหัสวันนี้นะครับ" (maybe a date or event?), and some advice about health, like drinking water, exercise, and not being stressed. There's also a part that mentions "โรคไพรค์ไข้เจ็บ" which might be a typo or a specific term. The user is asking if any of this content could be illegal.

Now, I need to check if any part of this text violates laws. Thai laws regarding content usually relate to defamation, incitement, hate speech, or illegal activities. The text seems to be general advice about health and well-being, possibly from a radio program. There's no mention of harmful activities, illegal substances, or anything that could be considered defamatory or inciting violence. The part about "โรคไพรค์" might be a mistranslation or a typo, maybe referring to a health condition. Since there's no explicit illegal content, the answer is likely "ไม่ผิด".
</think>

ไม่ผิด`;

// Backend extraction function (same as in API)
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
  
  return 'ไม่สามารถวิเคราะห์ได้';
}

// Frontend parser function (same as in component)
function parseOllamaResponse(response) {
  const sections = {
    thinking: '',
    summary: '',
    finalAnswer: ''
  }

  // Extract Thinking section from <think>...</think> tags
  const thinkTagMatch = response.match(/<think>([\s\S]*?)<\/think>/i)
  if (thinkTagMatch) {
    sections.thinking = thinkTagMatch[1].trim()
    
    // Extract the final answer after </think> tag
    const afterThinkMatch = response.match(/<\/think>\s*([\s\S]*?)$/i)
    if (afterThinkMatch) {
      sections.finalAnswer = afterThinkMatch[1].trim()
    }
  }

  return sections
}

// Test both functions
console.log('=== Backend Extraction Test ===');
const extractedResult = extractRiskResult(testResponse);
console.log('Extracted Result:', extractedResult);

console.log('\n=== Frontend Parser Test ===');
const parsedSections = parseOllamaResponse(testResponse);
console.log('Parsed Sections:');
console.log('- Thinking:', parsedSections.thinking.substring(0, 100) + '...');
console.log('- Final Answer:', parsedSections.finalAnswer);

console.log('\n=== Expected vs Actual ===');
console.log('Expected Backend Result: ไม่ผิด');
console.log('Actual Backend Result:', extractedResult);
console.log('Expected Frontend Final Answer: ไม่ผิด');
console.log('Actual Frontend Final Answer:', parsedSections.finalAnswer);

console.log('\n=== Test Status ===');
const backendCorrect = extractedResult === 'ไม่ผิด';
const frontendCorrect = parsedSections.finalAnswer === 'ไม่ผิด';
console.log('Backend Extraction:', backendCorrect ? '✅ PASS' : '❌ FAIL');
console.log('Frontend Parsing:', frontendCorrect ? '✅ PASS' : '❌ FAIL');
console.log('Overall:', (backendCorrect && frontendCorrect) ? '✅ ALL TESTS PASS' : '❌ SOME TESTS FAIL');
