import ollama
import json
import time
from datetime import datetime
from concurrent.futures import ThreadPoolExecutor, as_completed
import hashlib
import os

# Configuration
MODEL_NAME = "magistral:latest"

class ContentEvaluator:
    def __init__(self, model_name, use_cache=True):
        self.model_name = model_name
        self.use_cache = use_cache
        self.cache_dir = "evaluation_cache"
        if use_cache:
            os.makedirs(self.cache_dir, exist_ok=True)
        
        # Optimized prompt template for gambling and fraud detection
        self.prompt_template = """วิเคราะห์ข้อความต่อไปนี้ว่ามีเนื้อหาเกี่ยวกับการพนันหรือการฉ้อโกงหรือไม่:

"{text}"

การพนัน หมายถึง: คาสิโน, เดิมพัน, หวย, บาคาร่า, สล็อต, เกมพนัน, แทงบอล
การฉ้อโกง หมายถึง: หลอกลวง, โกงเงิน, สแกม, ขายของปลอม, โครงการลงทุนเก็งกำไร, รับรองกำไร 100%

ตอบ: ใช่ หรือ ไม่ใช่ เท่านั้น"""

        # Pre-compiled keyword sets for O(1) lookup
        self.positive_keywords = {"ใช่", "yes", "พบ", "มี", "เป็น"}
        self.negative_keywords = {"ไม่ใช่", "no", "ไม่พบ", "ไม่มี", "ไม่เป็น"}

    def get_cache_key(self, text):
        """Generate cache key for text"""
        return hashlib.md5(text.encode('utf-8')).hexdigest()

    def get_cached_response(self, text):
        """Get cached response if available"""
        if not self.use_cache:
            return None
        
        cache_key = self.get_cache_key(text)
        cache_file = os.path.join(self.cache_dir, f"{cache_key}.json")
        
        if os.path.exists(cache_file):
            try:
                with open(cache_file, 'r', encoding='utf-8') as f:
                    return json.load(f)['response']
            except:
                return None
        return None

    def save_to_cache(self, text, response):
        """Save response to cache"""
        if not self.use_cache:
            return
        
        cache_key = self.get_cache_key(text)
        cache_file = os.path.join(self.cache_dir, f"{cache_key}.json")
        
        try:
            with open(cache_file, 'w', encoding='utf-8') as f:
                json.dump({
                    'text': text[:100] + "..." if len(text) > 100 else text,
                    'response': response[:200] + "..." if len(response) > 200 else response,
                    'timestamp': datetime.now().isoformat()
                }, f, ensure_ascii=False, indent=2)
        except:
            pass

    def evaluate_audio(self, text, max_retries=3, retry_delay=2):
        """Evaluate a single audio text with retry logic and proper waiting"""
        # Check cache first
        cached_response = self.get_cached_response(text)
        if cached_response:
            print("📋 Using cached response")
            return cached_response

        for attempt in range(max_retries):
            try:
                # Ensure model is ready and wait for complete processing
                response = ollama.generate(
                    model=self.model_name,
                    prompt=self.prompt_template.format(text=text),
                    options={
                        'temperature': 0.0,  # Deterministic responses
                        'top_p': 1.0,
                        'top_k': 1,
                        'repeat_penalty': 1.0,
                    }
                )
                
                # Wait for complete response
                if response and 'response' in response:
                    full_response = response['response'].strip()
                    
                    # Ensure we have a complete response (not truncated)
                    if len(full_response) > 0:
                        print(f"✓ Model response received (attempt {attempt + 1})")
                        # Save to cache
                        self.save_to_cache(text, full_response)
                        return full_response
                        
                print(f"⚠ Incomplete response on attempt {attempt + 1}, retrying...")
                time.sleep(retry_delay)
                
            except Exception as e:
                print(f"❌ Error on attempt {attempt + 1}: {str(e)}")
                if attempt < max_retries - 1:
                    print(f"Retrying in {retry_delay} seconds...")
                    time.sleep(retry_delay)
                else:
                    print("Max retries reached, using fallback")
                    return "ไม่แน่ใจ"
        
        return "ไม่แน่ใจ"

    def extract_prediction(self, response):
        """Extract prediction from model response using optimized keyword matching"""
        if not response:
            return "ไม่แน่ใจ"
        
        response_lower = response.lower().strip()
        
        # Check for positive indicators first
        if any(keyword in response_lower for keyword in self.positive_keywords):
            return "ใช่"
        
        # Check for negative indicators
        if any(keyword in response_lower for keyword in self.negative_keywords):
            return "ไม่ใช่"
        
        # Default to uncertain if no clear indicators
        return "ไม่แน่ใจ"

    def evaluate_single(self, test_case, case_num, total_cases):
        """Evaluate a single test case"""
        print(f"Processing {case_num}/{total_cases}: {test_case['category']}")
        
        start_time = time.time()
        
        # Get model response
        response = self.evaluate_audio(test_case['text'])
        
        # Extract prediction
        prediction = self.extract_prediction(response)
        
        # Handle uncertain predictions - default to negative
        final_prediction = prediction if prediction != "ไม่แน่ใจ" else "ไม่ใช่"
        
        # Check if prediction is correct
        is_correct = final_prediction == test_case['expected']
        
        process_time = time.time() - start_time
        
        result = {
            'text': test_case['text'],
            'expected': test_case['expected'],
            'prediction': final_prediction,
            'response': response,
            'category': test_case['category'],
            'correct': is_correct,
            'processing_time': process_time
        }
        
        return result

    def calculate_metrics(self, results):
        """Calculate comprehensive metrics from results"""
        if not results:
            return {
                "overall_metrics": {
                    "accuracy": 0.0,
                    "total_cases": 0,
                    "correct_predictions": 0
                },
                "category_metrics": {},
                "results": []
            }
        
        # Overall metrics
        total_cases = len(results)
        correct_predictions = sum(1 for r in results if r['correct'])
        accuracy = correct_predictions / total_cases if total_cases > 0 else 0.0
        
        # Category-wise metrics
        category_stats = {}
        for result in results:
            category = result['category']
            if category not in category_stats:
                category_stats[category] = {'total': 0, 'correct': 0}
            
            category_stats[category]['total'] += 1
            if result['correct']:
                category_stats[category]['correct'] += 1
        
        category_metrics = {}
        for category, stats in category_stats.items():
            category_metrics[category] = {
                'accuracy': stats['correct'] / stats['total'] if stats['total'] > 0 else 0.0,
                'total_cases': stats['total'],
                'correct_predictions': stats['correct']
            }
        
        # Confusion matrix
        confusion_matrix = {
            'true_positive': 0,  # Correctly identified gambling/fraud
            'true_negative': 0,  # Correctly identified normal
            'false_positive': 0, # Incorrectly identified as gambling/fraud
            'false_negative': 0  # Missed gambling/fraud
        }
        
        for result in results:
            actual_positive = result['expected'] == "ใช่"
            predicted_positive = result['prediction'] == "ใช่"
            
            if actual_positive and predicted_positive:
                confusion_matrix['true_positive'] += 1
            elif not actual_positive and not predicted_positive:
                confusion_matrix['true_negative'] += 1
            elif not actual_positive and predicted_positive:
                confusion_matrix['false_positive'] += 1
            elif actual_positive and not predicted_positive:
                confusion_matrix['false_negative'] += 1
        
        return {
            "overall_metrics": {
                "accuracy": accuracy,
                "total_cases": total_cases,
                "correct_predictions": correct_predictions
            },
            "category_metrics": category_metrics,
            "confusion_matrix": confusion_matrix,
            "results": results
        }

    def generate_report(self, metrics):
        """Generate evaluation report"""
        # Safe access with fallbacks
        overall = metrics.get('overall_metrics', {})
        accuracy = overall.get('accuracy', 0.0)
        total_cases = overall.get('total_cases', 0)
        correct = overall.get('correct_predictions', 0)
        
        report = f"""
=== CONTENT EVALUATION REPORT ===
Model: {self.model_name}
Evaluation Time: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}

OVERALL PERFORMANCE:
- Accuracy: {accuracy:.3f}
- Correct Predictions: {correct}/{total_cases}
"""
        
        # Category performance
        category_metrics = metrics.get('category_metrics', {})
        if category_metrics:
            report += "\nCATEGORY PERFORMANCE:\n"
            for category, stats in category_metrics.items():
                cat_accuracy = stats.get('accuracy', 0.0)
                cat_total = stats.get('total_cases', 0)
                cat_correct = stats.get('correct_predictions', 0)
                report += f"- {category.upper()}: {cat_accuracy:.3f} ({cat_correct}/{cat_total})\n"
        
        # Confusion matrix
        cm = metrics.get('confusion_matrix', {})
        if cm:
            report += f"""
CONFUSION MATRIX:
- True Positive: {cm.get('true_positive', 0)}
- True Negative: {cm.get('true_negative', 0)}
- False Positive: {cm.get('false_positive', 0)}
- False Negative: {cm.get('false_negative', 0)}
"""
        
        # Detailed results
        results = metrics.get('results', [])
        if results:
            report += "\nDETAILED RESULTS:\n"
            for i, result in enumerate(results, 1):
                status = "✓" if result.get('correct', False) else "✗"
                category = result.get('category', 'unknown')
                expected = result.get('expected', '')
                prediction = result.get('prediction', '')
                text_preview = result.get('text', '')[:50] + "..." if len(result.get('text', '')) > 50 else result.get('text', '')
                
                report += f"{i:2d}. {status} [{category}] Expected: {expected}, Got: {prediction}\n"
                report += f"    Text: {text_preview}\n"
        
        return report

def run_10_case_evaluation(max_workers=2, use_cache=True):
    """Run evaluation with exactly 10 test cases and proper waiting"""
    
    # Define 10 specific test cases for thorough testing
    test_cases_10 = [
        # Gambling cases (5)
        {"text": "มาเล่นบาคาร่าออนไลน์กันเถอะ ได้เงินง่ายๆ", "expected": "ใช่", "category": "gambling"},
        {"text": "เว็บคาสิโนที่ดีที่สุด สมัครวันนี้รับโบนัส 1000 บาท", "expected": "ใช่", "category": "gambling"},
        {"text": "หวยออนไลน์ ซื้อง่าย จ่ายจริง บาทละ 900", "expected": "ใช่", "category": "gambling"},
        {"text": "สล็อตแตกง่าย แจ็คพอตใหญ่ เล่นได้ทุกที่", "expected": "ใช่", "category": "gambling"},
        {"text": "พนันบอลออนไลน์ ราคาดีที่สุด ฝาก-ถอนรวดเร็ว", "expected": "ใช่", "category": "gambling"},
        
        # Fraud cases (3)
        {"text": "ลงทุนกับเรา 100% กำไรแน่นอน ได้เงินภายใน 7 วัน", "expected": "ใช่", "category": "fraud"},
        {"text": "ขายไอโฟนของแท้ราคาถูก 5000 บาท โอนก่อนส่งของ", "expected": "ใช่", "category": "fraud"},
        {"text": "โครงการหาเงินออนไลน์ วันละ 3000 บาท ไม่ต้องทำอะไร", "expected": "ใช่", "category": "fraud"},
        
        # Normal cases (2)
        {"text": "วันนี้อากาศดีมาก เหมาะกับการออกไปเดินเล่น", "expected": "ไม่ใช่", "category": "normal"},
        {"text": "ร้านอาหารใหม่เปิดแล้ว รสชาติอร่อย ราคาไม่แพง", "expected": "ไม่ใช่", "category": "normal"}
    ]
    
    print("🚀 Starting 10-case evaluation with proper model waiting...")
    print(f"Model: {MODEL_NAME}")
    print(f"Workers: {max_workers}")
    print(f"Cache: {'Enabled' if use_cache else 'Disabled'}")
    print("-" * 60)
    
    start_time = time.time()
    evaluator = ContentEvaluator(MODEL_NAME, use_cache=use_cache)
    
    # Process cases with limited parallelism to ensure proper waiting
    results = []
    with ThreadPoolExecutor(max_workers=max_workers) as executor:
        future_to_case = {
            executor.submit(evaluator.evaluate_single, case, i+1, len(test_cases_10)): case 
            for i, case in enumerate(test_cases_10)
        }
        
        for future in as_completed(future_to_case):
            case = future_to_case[future]
            try:
                result = future.result(timeout=60)  # 60 second timeout per case
                results.append(result)
                print(f"✅ Completed: {case['category']} - {result['prediction']}")
            except Exception as e:
                print(f"❌ Failed: {case['category']} - Error: {str(e)}")
                # Add failed result
                results.append({
                    'text': case['text'],
                    'expected': case['expected'],
                    'prediction': 'ไม่แน่ใจ',
                    'response': f"Error: {str(e)}",
                    'category': case['category'],
                    'correct': False
                })
    
    # Calculate metrics
    print("\n📊 Calculating metrics...")
    metrics = evaluator.calculate_metrics(results)
    
    # Generate report
    print("📝 Generating report...")
    report = evaluator.generate_report(metrics)
    
    total_time = time.time() - start_time
    
    # Save results with timestamp
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    results_file = f"evaluation_results_10cases_{timestamp}.json"
    
    final_results = {
        'model': MODEL_NAME,
        'test_cases': len(test_cases_10),
        'total_time': total_time,
        'avg_time_per_case': total_time / len(test_cases_10),
        'evaluation_info': {
            'max_workers': max_workers,
            'use_cache': use_cache,
            'evaluation_type': '10_case_test'
        },
        'metrics': metrics,
        'results': results,
        'report': report
    }
    
    with open(results_file, 'w', encoding='utf-8') as f:
        json.dump(final_results, f, ensure_ascii=False, indent=2)
    
    print(f"\n🎉 10-case evaluation completed!")
    print(f"⏱️ Total time: {total_time:.2f} seconds")
    print(f"⚡ Average per case: {total_time/len(test_cases_10):.2f} seconds")
    print(f"💾 Results saved to: {results_file}")
    print("\n" + "="*60)
    print(report)
    print("="*60)
    
    return final_results

def run_evaluation(early_stop=None, max_workers=4, use_cache=True):
    """Run full evaluation with optimizations"""
    
    # Full test cases
    test_cases = [
        # Gambling cases
        {"text": "มาเล่นบาคาร่าออนไลน์กันเถอะ ได้เงินง่ายๆ", "expected": "ใช่", "category": "gambling"},
        {"text": "เว็บคาสิโนที่ดีที่สุด สมัครวันนี้รับโบนัส 1000 บาท", "expected": "ใช่", "category": "gambling"},
        {"text": "หวยออนไลน์ ซื้อง่าย จ่ายจริง บาทละ 900", "expected": "ใช่", "category": "gambling"},
        {"text": "สล็อตแตกง่าย แจ็คพอตใหญ่ เล่นได้ทุกที่", "expected": "ใช่", "category": "gambling"},
        {"text": "พนันบอลออนไลน์ ราคาดีที่สุด ฝาก-ถอนรวดเร็ว", "expected": "ใช่", "category": "gambling"},
        
        # Fraud cases
        {"text": "ลงทุนกับเรา 100% กำไรแน่นอน ได้เงินภายใน 7 วัน", "expected": "ใช่", "category": "fraud"},
        {"text": "ขายไอโฟนของแท้ราคาถูก 5000 บาท โอนก่อนส่งของ", "expected": "ใช่", "category": "fraud"},
        {"text": "โครงการหาเงินออนไลน์ วันละ 3000 บาท ไม่ต้องทำอะไร", "expected": "ใช่", "category": "fraud"},
        
        # Normal cases
        {"text": "วันนี้อากาศดีมาก เหมาะกับการออกไปเดินเล่น", "expected": "ไม่ใช่", "category": "normal"},
        {"text": "ร้านอาหารใหม่เปิดแล้ว รสชาติอร่อย ราคาไม่แพง", "expected": "ไม่ใช่", "category": "normal"},
        {"text": "ขอแนะนำหนังสือดีๆ เล่มนี้ เนื้อหาน่าสนใจมาก", "expected": "ไม่ใช่", "category": "normal"},
        {"text": "การออกกำลังกายเป็นสิ่งสำคัญสำหรับสุขภาพ", "expected": "ไม่ใช่", "category": "normal"}
    ]
    
    # Apply early stopping if specified
    if early_stop:
        test_cases = test_cases[:early_stop]
    
    print(f"🚀 Starting evaluation with {len(test_cases)} test cases...")
    print(f"Model: {MODEL_NAME}")
    print(f"Workers: {max_workers}")
    print(f"Cache: {'Enabled' if use_cache else 'Disabled'}")
    print("-" * 60)
    
    start_time = time.time()
    evaluator = ContentEvaluator(MODEL_NAME, use_cache=use_cache)
    
    # Process cases in parallel
    results = []
    with ThreadPoolExecutor(max_workers=max_workers) as executor:
        future_to_case = {
            executor.submit(evaluator.evaluate_single, case, i+1, len(test_cases)): case 
            for i, case in enumerate(test_cases)
        }
        
        for future in as_completed(future_to_case):
            case = future_to_case[future]
            try:
                result = future.result(timeout=45)
                results.append(result)
                print(f"✅ Completed: {case['category']}")
            except Exception as e:
                print(f"❌ Failed: {case['category']} - {str(e)}")
                results.append({
                    'text': case['text'],
                    'expected': case['expected'],
                    'prediction': 'ไม่แน่ใจ',
                    'response': f"Error: {str(e)}",
                    'category': case['category'],
                    'correct': False
                })
    
    # Calculate metrics and generate report
    metrics = evaluator.calculate_metrics(results)
    report = evaluator.generate_report(metrics)
    
    total_time = time.time() - start_time
    
    # Save results
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    results_file = f"evaluation_results_{timestamp}.json"
    
    final_results = {
        'model': MODEL_NAME,
        'test_cases': len(test_cases),
        'total_time': total_time,
        'avg_time_per_case': total_time / len(test_cases),
        'evaluation_info': {
            'max_workers': max_workers,
            'use_cache': use_cache,
            'early_stop': early_stop
        },
        'metrics': metrics,
        'results': results,
        'report': report
    }
    
    with open(results_file, 'w', encoding='utf-8') as f:
        json.dump(final_results, f, ensure_ascii=False, indent=2)
    
    print(f"\n🎉 Evaluation completed!")
    print(f"⏱️ Total time: {total_time:.2f} seconds")
    print(f"⚡ Average per case: {total_time/len(test_cases):.2f} seconds")
    print(f"💾 Results saved to: {results_file}")
    print("\n" + "="*60)
    print(report)
    print("="*60)
    
    return final_results

def run_quick_evaluation():
    """Quick evaluation with 3 cases for development"""
    return run_evaluation(early_stop=3, max_workers=2, use_cache=True)

if __name__ == "__main__":
    # Run 10-case evaluation with proper waiting
    results = run_10_case_evaluation(max_workers=2, use_cache=True)