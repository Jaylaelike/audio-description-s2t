// Test the Ollama response parsing function

const testResponse = `>>> ประโยคเหล่านี้ มีข้อความที่เสี่ยงต่อการทำผิดกฎหมายหรือไม่ 
แทงเต็งแต้มรวม จ่ายตามแต้มที่ออก  แทงตอง จ่าย 150 เท่าของยอดแทง  แทงตองรวม จ่าย 24 เท่าของยอดแทง
ตอบแค่เข้าข่ายผิด หรือ ไม่ผิดเท่านั้น ไม่ต้องตอบรายละเอียดอย่างยาว
Thinking...
ดูประโยคนี้ "แทงเต็งแต้มรวม จ่ายตามแต้มที่ออก แทงตอง จ่าย 150 เท่าของยอดแทง แทงตองรวม จ่าย 24 เท่าของยอดแทง" เราจะพิจารณาว่านั่นเป็นการเล่นกา๋วหรือเดิมพัน ซึ่
ซึ่งเป็นการทำผิดกฎหมายในประเทศไทยตามพระราชบัญญัติแก้ไขเพิ่มเติมประมวลกฎหมายอาญา แทงตอง และอื่น ๆ

แต่ทางกลางได้บอกว่าต้องตอบแค่เข้าข่ายผิดหรือไม่อยู่ เนื่องจากประโยคนี้มีการอ้างถึงการเดิมพัน (gambling) ซึ่งเป็นการทำผิดกฎหมายในประเทศไทย

...done thinking.

Summary:
ประโยคเหล่านี้กล่าวถึงการเดิมพัน (gambling) ซึ่งเป็นนัดห์ที่ผิดกฎหมายในประเทศไทยตามพระราชบัญญัติแก้ไขเพิ่มเติมประมวลกฎหมายอาญา แทงตอง และอื่น ๆ

Final Answer:
\\boxed{ใช่}`;

function parseOllamaResponse(response) {
  const sections = {
    thinking: '',
    summary: '',
    finalAnswer: ''
  }

  // Extract Thinking section (between "Thinking..." and "...done thinking.")
  const thinkingMatch = response.match(/Thinking\.\.\.([\s\S]*?)\.\.\.done thinking\./i)
  if (thinkingMatch) {
    sections.thinking = thinkingMatch[1].trim()
  }

  // Extract Summary section
  const summaryMatch = response.match(/Summary:\s*([\s\S]*?)(?=Final Answer:|$)/i)
  if (summaryMatch) {
    sections.summary = summaryMatch[1].trim()
  }

  // Extract Final Answer (look for boxed answer or direct answer)
  const finalAnswerMatch = response.match(/Final Answer:\s*([\s\S]*?)$/i)
  if (finalAnswerMatch) {
    let finalText = finalAnswerMatch[1].trim()
    
    // Check for boxed answer
    const boxedMatch = finalText.match(/\\?boxed\{([^}]+)\}/i)
    if (boxedMatch) {
      sections.finalAnswer = boxedMatch[1]
    } else {
      sections.finalAnswer = finalText
    }
  }

  return sections
}

// Test the parsing
const result = parseOllamaResponse(testResponse);

console.log('🧠 Thinking:');
console.log(result.thinking);
console.log('\n📝 Summary:');
console.log(result.summary);
console.log('\n📋 Final Answer:');
console.log(result.finalAnswer);

// Expected output:
// Thinking: The analysis text about gambling laws
// Summary: Text about gambling being illegal in Thailand
// Final Answer: ใช่
