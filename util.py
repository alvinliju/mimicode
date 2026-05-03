def fizzbuzz(n):
    """
    Return a list of FizzBuzz strings for numbers 1 through n.
    
    Returns "Fizz" for multiples of 3, "Buzz" for multiples of 5,
    "FizzBuzz" for multiples of both, and the number as a string otherwise.
    
    Args:
        n: Upper bound (inclusive)
    
    Returns:
        List of strings representing FizzBuzz values for 1..n
    """
    result = []
    for i in range(1, n + 1):
        if i % 15 == 0:
            result.append("FizzBuzz")
        elif i % 3 == 0:
            result.append("Fizz")
        elif i % 5 == 0:
            result.append("Buzz")
        else:
            result.append(str(i))
    return result
