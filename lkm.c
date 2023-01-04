#include <linux/module.h>
#include <linux/gpio.h>
#include <linux/interrupt.h>

static bool	State = 0;

static unsigned int OffLed = 27;
static unsigned int GreenLed = 24;
static unsigned int YellowLed = 15;
static unsigned int RedLed = 4;

static unsigned int Button = 17;
static unsigned int Irqnum = 0;
static unsigned int Counter = 0;


/*  Handle interrupt  - button push event */
static irq_handler_t piirq_irq_handler(unsigned int irq, void *dev_id, struct pt_regs *regs){
    /* Toogle LED */
   gpio_set_value(OffLed, State);
   State = !State;
   gpio_set_value(GreenLed, State);
   gpio_set_value(YellowLed, State);
   gpio_set_value(RedLed, State);
   
   printk(KERN_INFO "piirq: Offled state is : [%d] ", gpio_get_value(OffLed));
   printk(KERN_INFO "piirq: button state is : [%d] ", gpio_get_value(Button));

   Counter++;
   return (irq_handler_t) IRQ_HANDLED;
}

void init_single_gpio(unsigned int pin, char * string, int start_value)
{
	gpio_request(pin,string);
	gpio_direction_output(pin,start_value);
	gpio_export(pin, false);
}

void close_single_gpio(unsigned int pin)
{
   gpio_set_value(pin, 0);
   gpio_unexport(pin);
   gpio_free(pin);
}

int __init piirq_init(void){
	int result = 0;
    pr_info("%s\n", __func__);
    /* https://www.kernel.org/doc/Documentation/pinctrl.txt */
	printk("piirq: IRQ Test");
    printk(KERN_INFO "piirq: Initializing driver\n");

    if (!gpio_is_valid(OffLed) || !gpio_is_valid(GreenLed) || !gpio_is_valid(YellowLed) || !gpio_is_valid(RedLed)){
    	printk(KERN_INFO "piirq: invalid GPIO\n");
    return -ENODEV;
   }

	/* Make it appear in /sys/class/gpio/gpio16 for echo 0 > value */
    	init_single_gpio(OffLed,"OffLed",1);
	init_single_gpio(GreenLed,"GreenLed",0);
	init_single_gpio(YellowLed,"YellowLed",0);
	init_single_gpio(RedLed,"RedLed",0);
	/*As the button also includes debounce instruction, it was left separately*/
	gpio_request(Button, "Button");
	gpio_direction_input(Button);
	gpio_set_debounce(Button, 700); /* Adjust this number to sync with circut */
	gpio_export(Button, false);


    Irqnum = gpio_to_irq(Button);
    printk(KERN_INFO "piirq: The button is mapped to IRQ: %d\n", Irqnum);

    result = request_irq(Irqnum,
		  (irq_handler_t) piirq_irq_handler, /* pointer to the IRQ handler method */
		  IRQF_TRIGGER_RISING,
		  "piirq_handler",    /* See this string from user console to identify: cat /proc/interrupts */
		  NULL);

    printk("piirq loaded\n");
    return 0;
}
void __exit piirq_exit(void){
   
	close_single_gpio(OffLed);
	close_single_gpio(RedLed);
	close_single_gpio(YellowLed);
	close_single_gpio(GreenLed);
	free_irq(Irqnum, NULL);
 	close_single_gpio(Button);  	
	printk("piirq unloaded\n");
}
module_init(piirq_init);
module_exit(piirq_exit);
MODULE_LICENSE("GPL");
MODULE_AUTHOR("Hubert Januszewski CMP408");
MODULE_DESCRIPTION("Module for CPU utilisation display using LEDs and hybrid cloud control");
MODULE_VERSION("0.1");
