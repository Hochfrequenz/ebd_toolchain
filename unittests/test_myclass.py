from ebd_toolchain.mymodule import MyClass


class TestMyClass:
    """
    A class with pytest unit tests.
    """

    def test_something(self) -> None:
        my_class = MyClass()
        assert my_class.do_something() == "abc"
